# Hermes — Cognitive Architecture Design (Cognition Layer)

> **Scope.** This document specifies the *cognition* of Hermes' autonomous agents:
> how they **reason, plan, research, verify, remember, and collaborate**. It is the
> layer *inside* the agent boxes drawn in `HERMES_DESIGN.md §12.12`. It does **not**
> cover storage schemas, collector HTTP details, scheduler wiring, or renderer
> Markdown formatting — those live in the system design and the implementation.
>
> **Authority.** `HERMES_DESIGN.md §11` (quality-first rubric) and `§12` (agent
> split + capability enhancements) are authoritative. Every cognitive mechanism
> below must map to at least one dimension of the §11.1 rubric:
> **Coverage · Accuracy/Verification · Depth · Synthesis · Usefulness · Trust**.
> If a mechanism maps to none, it is cut.
>
> **Hard constraints carried from the system design:**
> - No agent-runtime framework (no Autogen/CrewAI/LangGraph). An "agent" is a
>   focused `async` module with one job, its own prompt, and an LLM role.
> - Memory is the set of persistent stores Hermes already writes (SQLite corpus +
>   analyses, Qdrant vectors, trend snapshots, KG). No separate memory service.
> - Research loops and RAG are gated and **partial-tolerant**: a failed sub-step
>   never blocks the report; it is flagged, not fatal.
> - The orchestrator is a linear flow plus one bounded Critic→Rewrite loop (and one
>   bounded Verification→Research escalation). Easy to test and resume.

---

## 1. Cognitive Principles (rules every agent obeys)

**P1 — Quality is the only acceptance test.** Each agent's design is justified by
the rubric dimension(s) it raises. See §9 for the metric that proves it.

**P2 — Cheap determinism, expensive intelligence.** Use heuristics/SQL for anything
a deterministic rule does as well as an LLM (type tagging, ranking, dedup, trend
deltas). Spend the LLM budget on analysis, research, verification, critique, and
RAG-grounded writing — the places a model actually changes report quality.

**P3 — Every claim carries provenance + confidence.** A claim is not "true"; it is
`{text, sources[], confidence, status}`. Status ∈
`CORROBORATED | CONFLICTING | SINGLE_SOURCE | UNVERIFIABLE`. This is the Trust
differentiator vs Perplexity and is non-negotiable.

**P4 — Partial tolerance / graceful degradation.** Any agent may return a *partial*
result with an explicit `gaps[]` list. The orchestrator never aborts the run because
one sub-step failed. A research loop that can't find the original paper reports
"primary source not located" and moves on.

**P5 — Bounded cognition.** Every agent has hard budgets: token/cost cap, depth cap,
breadth cap, wall-clock cap. Cognition stops when a budget is hit, even mid-reason.
Budgets are allocated top-down by the Planning Agent (§6).

**P6 — Memory is read and written through one narrow bus.** Agents never touch raw
DB tables ad hoc. They call the `MemoryBus` operations in §2. This keeps memory
swappable and the agents testable against an in-memory fake.

**P7 — Provenance propagates across handoffs.** Each inter-agent message carries a
`provenance` block (§4). A claim verified by the Verification Agent keeps its
verification status when it reaches the Writer; the Writer cannot silently upgrade a
`SINGLE_SOURCE` claim to a confident statement.

---

## 2. Memory Model — the "remember" substrate

Hermes' long-term memory is the union of four persistent stores. There is **no
separate memory subsystem** (§12.8); "memory" is just disciplined access to stores
the pipeline already writes.

### 2.1 The four memory types

| Type | Store | What it holds | Cognitive role |
|---|---|---|---|
| **Episodic** | `reports/` + `run_manifests/` (SQLite `Report` row) | Past daily reports, what ran, cost, failures, coverage note | Continuity ("we covered X 3 months ago"), RAG context for the Writer, quality-loop baseline |
| **Semantic** | SQLite `Item` + `Analysis` + Qdrant vectors | The factual corpus: every collected item, its structured analysis, its embedding | Retrieval for research/verification/RAG; the knowledge base |
| **Structural** | KG `entities` + `relationships` (SQLite) | How actors relate: `released_by`, `beats`, `built_on`, `competes_with`, `cites`, `succeeds`… | Trend reasoning, rivalry/lineage synthesis, research-loop "find rivals" |
| **Temporal** | `TrendSnapshot` (SQLite) | Daily/weekly deltas, rising/fading topics, trajectories | "Compare with previous work", trend sections, novelty scoring |

### 2.2 `MemoryBus` — the only memory interface agents use

Conceptual contract (implemented as plain functions over the stores; not a service):

```
# READ
bus.recall_items(since, source_types[], top_k, threshold)   -> Item[]
bus.recall_similar(text|vector, top_k, threshold, exclude_ids[]) -> SearchHit[]   # Qdrant
bus.recall_analysis(item_id) -> Analysis | None
bus.recall_reports(since, query?, top_k) -> Report[]          # RAG context
bus.recall_trends(since, window) -> TrendSnapshot[]
bus.traverse_kg(entity, predicates[], max_hops) -> Relation[]
bus.novelty_signal(entity|topic, window) -> float             # from trend + KG first_seen

# WRITE
bus.store_item(item)
bus.store_analysis(analysis)            # idempotent by (item_id, analyzer_version)
bus.upsert_vector(item_id, vector)
bus.assert_entity(entity)               # conservative merge (§2.4)
bus.assert_relation(relation)           # high-confidence only
bus.commit_trend(snapshot)
bus.commit_report(report, manifest)
```

### 2.3 Access patterns per agent

| Agent | Reads | Writes |
|---|---|---|
| Discovery | source-health history (which collectors failed recently) | run manifest (per-source status) |
| Ingest | — (writes) | Item, vector, dedup aliases |
| Planning | Items, Trends (novelty), KG (first_seen), report profile | InvestigationPlan (in-memory; not persisted as a store) |
| Research | Items, similar (Qdrant), KG (rivals/lineage), past reports (RAG) | Analysis (+ its claims/entities), KG entities/relations |
| Verification | Analysis claims, similar items (Qdrant), KG | verification annotations on claims (back into Analysis) |
| Trend | current corpus, prior TrendSnapshots, KG | TrendSnapshot, KG edges |
| Writer | Analyses, verifications, clusters, trends, past reports (RAG), KG | Draft ReportModel (in-memory) |
| Critic | Draft + source Analyses/verifications | CritiqueReport (in-memory) |
| Archive | everything | Report row, KG edges, TrendSnapshot, coverage note |

### 2.4 KG resolution rules (quality guard)

Poor entity resolution *degrades* quality (wrong `competes_with`). Rules:
- Normalize names (lowercase, strip punctuation, collapse whitespace); keep `aliases_json`.
- Merge two entities only on **high-confidence** match (exact normalized name, or
  LLM-confirmed alias). Otherwise create a new entity.
- Never invent a `relation`. A relation is written only if the analysis that
  produced it cited a source, and `confidence` is set from source count/type.
- `predicate` is drawn from the closed set in §12.4; the LLM may not coin new ones.

---

## 3. Shared Reasoning Primitives

These are the cognitive building blocks agents compose. They are *patterns*, not
frameworks — each is a prompt + a control loop implemented in the agent module.

| Primitive | Shape | Used by | Rubric dim |
|---|---|---|---|
| **Chain-of-Thought (CoT)** | "think step by step; show reasoning; then emit structured answer" | Planning, Research synthesis, Trend narration | Depth |
| **ReAct research loop** | `thought → action(tool) → observation →` repeat, bounded | Research Agent | Depth, Coverage |
| **Claim triangulation** | extract claims → retrieve independent sources → score corroboration | Verification Agent | Accuracy, Trust |
| **Rubric-conditioned critique** | judge draft against the 6-dim rubric → structured fixes | Critic Agent | Accuracy, Usefulness |
| **Hierarchical decomposition** | split run goal → per-item depth tiers + sub-questions + budget | Planning Agent | Usefulness, Synthesis |
| **RAG grounding** | retrieve continuity context → bind every claim to a retrieved fact | Writer Agent | Synthesis, Trust |
| **Confidence calibration** | force explicit confidence + source count on every claim | all claim-emitting agents | Trust |

**When NOT to use LLM reasoning:** type tagging (heuristic), ranking (heuristic
prestige×recency×stars/citations×novelty), dedup, trend *deltas* (SQL), section
ordering (explicit list). These are P2.

---

## 4. Communication Protocol — the "collaborate" layer

### 4.1 `RunContext` (shared, injected once)

```
RunContext {
  run_id, date, profile: ReportProfile,
  bus: MemoryBus, router: LLMRouter, embedder: Embedder,
  budgets: BudgetLedger,            # remaining tokens per agent + global
  logger: structlog,
}
```

### 4.2 Handoff envelope

Every inter-agent message is wrapped so provenance propagates (P7):

```
Handoff {
  from_agent: str
  to_agent: str
  run_id: str
  ts: datetime
  payload: <typed per edge>          # see §4.3
  provenance: {
    sources_used: list[SourceRef]    # primary vs signal, with URLs
    confidence: float
    partial: bool
    gaps: list[str]                  # what could not be obtained
  }
}
```

### 4.3 Edge payloads (the agent graph)

```
Discovery  ──▶ Ingest        : RawItem[]
Ingest     ──▶ Planning      : Item[]                      (+vectors in Qdrant)
Planning   ──▶ Research      : InvestigationPlan           (list[InvestigationTask])
Research   ──▶ Verification  : Analysis[]                  (claims extracted, unverified)
Verification──▶ Trend        : VerifiedAnalysis[]          (claims now carry status)
Trend      ──▶ Writer        : TrendReport
Research/Verification/Trend ─▶ Writer : all consumed via MemoryBus (Writer reads bus, not messages, for bulk)
Writer     ──▶ Critic        : DraftReport (ReportModel)
Critic     ──▶ Writer        : CritiqueReport (structured fixes)
Writer     ──▶ Renderer      : FinalReportModel
Renderer   ──▶ Sink(s)       : Markdown (+ Obsidian/email/…)
Archive    : consumes bus (Report, KG, TrendSnapshot, coverage note)
```

**Why Writer reads the bus instead of a giant message:** the Writer needs the whole
corpus context (all analyses, clusters, trends, RAG history). Passing that as a
message is wasteful; the Writer queries `bus` directly. Handoffs above are the
*control* signals; bulk data flows through memory.

### 4.4 Re-entrancy / escalation (bounded)

The flow is linear, but two bounded loops are allowed:

1. **Critic→Writer rewrite** (§12.6): Writer drafts → Critic returns fixes → Writer
   rewrites only flagged sections → Critic re-checks **once**. Max 2 critique passes.
2. **Verification→Research escalation** (new, bounded): if Verification marks a
   *high-severity* `CONFLICTING` or `UNVERIFIABLE` claim on a DEEP/EXHAUSTIVE item,
   it emits `escalation: RESEARCH_CONFLICT` with a focused question. The orchestrator
   re-invokes Research for that single item with a narrowed plan (one extra loop,
   capped). This directly raises Accuracy and is partial-tolerant: if the re-loop
   fails, the claim stays `CONFLICTING`/`UNVERIFIABLE` and is reported as such.

No other back-edges. This keeps the graph acyclic except for two explicitly bounded
cycles — testable and resumable.

---

## 5. Agent Specifications

For each agent: **Role · Responsibilities · Inputs · Outputs · Reasoning · Prompt
(skeleton) · Tools · Memory · Stopping · Metrics · Failure/degradation.**

---

### 5.1 Discovery Agent

**Role.** Sampler. Maximizes *Coverage* by running every enabled collector and
surfacing raw items without dropping the run when a source dies.

**Responsibilities.** Invoke enabled collectors concurrently; apply per-source
timeout + retry-once + skip-on-failure; record per-source health into the run
manifest; pass raw items forward.

**Inputs.** `RunContext` (enabled collector set from `profile`, date, per-source
timeout from config).

**Outputs.** `RawItem[]` + `provenance.sources_used` + per-source status in manifest.

**Reasoning.** None beyond scheduling. Pure concurrency + fault isolation (P4).

**Prompt.** None (no LLM call).

**Tools.** Collector adapters (arXiv, RSS, GitHub trending/releases, HF, OpenReview,
PwC, Semantic Scholar, HN, Reddit, X, Bluesky, YouTube…). Each behind
`timeout + retry_once`.

**Memory.** Reads source-health history (optional, to deprioritize flaky sources);
writes per-source status to run manifest.

**Stopping.** All collectors returned-or-timed-out-or-skipped; OR global collect
wall-clock budget hit (then return what's gathered so far, mark `partial`).

**Metrics (Coverage).** `sources_attempted`, `sources_ok`, `sources_failed`,
`raw_items`, `source_type_diversity` (distinct `source_type` count), `blind_spot`
check (did expected high-signal sources run?).

**Failure/degradation.** A dead API → skipped, logged, reported in Coverage note.
Never aborts run.

---

### 5.2 Ingest (cognitive aspects)

**Role.** Normalizer + deduper + embedder. Raises *Accuracy* (no duplicate stories)
and enables *Synthesis* (embeddings power clustering/verification/RAG).

**Responsibilities.** Exact dedup (sha256) → near-dup (SimHash, alias link) → embed
→ store `Item` + vector atomically.

**Inputs.** `RawItem[]`.

**Outputs.** `Item[]` (new + alias-linked), vectors in Qdrant.

**Reasoning.** Threshold decisions: SimHash bit-distance threshold for "near dup"
(configurable; conservative so we don't merge distinct stories). Alias, don't delete
— preserves provenance.

**Prompt.** None.

**Tools.** `Embedder` (configurable model, default small/fast), SQLite write, Qdrant
upsert.

**Memory.** Writes Item + vector + aliases. Reads prior Item hashes for exact dedup.

**Stopping.** All raw items processed; OR ingest budget hit (process highest-priority
first, mark rest `partial`).

**Metrics (Accuracy).** `dup_exact_removed`, `dup_near_aliased`, `embed_failures`
(flagged, item kept without vector), `new_items`.

**Failure/degradation.** Embed failure → keep item text, skip vector, flag (clustering
still works on text for that item via fallback).

---

### 5.3 Planning Agent (executive function)

**Role.** The brain of the run. Converts a flat item list into a *bounded,
quality-maximizing investigation plan*. Raises **Usefulness + Synthesis + Coverage
balance**.

**Responsibilities.**
1. Heuristic-rank every item (prestige × recency × stars/citations × novelty).
2. Assign each item a **depth tier** (§6.1) based on rank + profile + novelty signal.
3. For DEEP/EXHAUSTIVE items, decompose into **research questions / sub-investigations**.
4. Allocate the run's token budget across items (§6.3), capping per-item spend.
5. Enforce *coverage balance*: don't over-invest in one cluster — cap items pulled
   from a single cluster to keep ecosystem breadth.

**Inputs.** `Item[]`, `bus.recall_trends` (novelty), `bus.traverse_kg` (first_seen /
lineage), `profile` (top_k, depth, research_loops flag, budget).

**Outputs.** `InvestigationPlan` = `list[InvestigationTask]` (schema §6).

**Reasoning.** *Hierarchical decomposition* (§3) + *CoT* for tier assignment on
borderline items. The planner may use a **light** LLM call **only** for top-tier
tie-breaks and for generating research questions on DEEP items (P2: heuristic does
the bulk; LLM spends on the few that matter).

**Prompt (planner — tie-break / question generation only; the rank itself is heuristic):**

```
Role: Executive research planner for an autonomous AI-ecosystem report.
Goal: decide how deeply each candidate item should be investigated today,
      and what specific questions a deep investigation must answer.

Inputs:
  - candidate items with heuristic scores: {{items_with_scores}}
  - novelty signal from trend/KG: {{novelty}}
  - report profile: top_k={{top_k}}, depth={{depth}}, budget_tokens={{budget}}
  - existing clusters (avoid over-investing in one story): {{clusters}}

Rules:
  1. Assign a depth tier per item: SKIM | STANDARD | DEEP | EXHAUSTIVE.
     - SKIM: low-rank or duplicate-of-covered story.
     - STANDARD: solid item, gets typed analysis + verification.
     - DEEP: high-rank OR high-novelty; gets autonomous research loops + RAG.
     - EXHAUSTIVE: only via deep_dive profile or a single top item.
  2. For each DEEP/EXHAUSTIVE item, emit 1–4 research questions of the form
     "find the primary source / benchmark numbers / competing approach / lineage".
  3. Respect budget: total planned token cost MUST NOT exceed {{budget}}.
     If over, demote lowest-rank DEEP→STANDARD until within budget.
  4. Coverage balance: at most {{max_per_cluster}} items from one cluster.

Output (strict JSON, extra="forbid"):
{
  "tasks": [
    {"item_id": str, "tier": str, "questions": [str],
     "token_budget": int, "loop_depth_cap": int, "loop_breadth_cap": int}
  ],
  "rationale": str,            # CoT summary, for the run log
  "coverage_balance_ok": bool
}
```

**Tools.** Heuristic ranker (local), `bus.recall_trends`, `bus.traverse_kg`,
`bus.recall_similar` (for clustering/coverage balance), LLM `plan` role (tie-breaks
+ question gen only).

**Memory.** Reads trends + KG + similarity. Writes nothing persistent (plan is
in-memory; it lives in the run manifest for resume/debug).

**Stopping.** Plan covers all top-`top_k` items within budget, OR planner budget
exhausted (then emit plan for as many as fit, mark `partial` with `gaps` listing
unplanned items).

**Metrics (Usefulness/Synthesis).** `tier_distribution`, `budget_utilization`,
`coverage_balance_violations`, `planned_token_cost vs budget`, `novelty_capture`
(% of high-novelty items that got DEEP).

**Failure/degradation.** If LLM planner call fails → fall back to pure heuristic
tiering (rank → top_k DEEP, rest STANDARD). Plan still valid.

---

### 5.4 Research Agent (autonomous loops)

**Role.** The investigator. Turns a plan task into a *rich, sourced* analysis. The
single biggest **Depth** lever (§12.9).

**Responsibilities.** For each DEEP/EXHAUSTIVE task: run a bounded ReAct loop —
generate sub-questions → retrieve (collectors / Qdrant / KG) → read/extract →
update a working analysis → decide next action or stop. Produce the adaptive-schema
`Analysis` + extracted `Claim[]` + KG entities/relations.

**Inputs.** `InvestigationTask` (item + tier + questions + budgets), `RunContext`.

**Outputs.** `Analysis` (adaptive schema + `type_specific` blob) with `Claim[]`
attached; KG `entity`/`relation` writes; `provenance` with `sources_used` + `gaps`.

**Reasoning.** *ReAct research loop* (§3). Controller prompt picks the next action
from a closed action space given the working state and remaining budget:

```
ActionSpace = {
  RETRIEVE_PRIMARY,    # find the paper / announcement / repo
  RETRIEVE_REPO,       # implementation, code, weights
  RETRIEVE_BENCHMARK,  # numbers, leaderboards (PwC, etc.)
  RETRIEVE_COMMUNITY,  # HN/Reddit/X discussion, failure reports
  RETRIEVE_RIVALS,     # KG "competes_with"/"succeeds" → compare
  SYNTHESIZE,          # write/extend the analysis from gathered facts
  STOP
}
```

Loop invariant: every factual sentence added to the analysis must trace to a
`sources_used` entry (P3). If a question can't be answered after its retrieval
attempts, record the question in `gaps` and move on (P4).

**Prompt (research controller — one iteration):**

```
Role: Autonomous research investigator. You build a sourced, two-altitude analysis.
You NEVER assert a fact without a retrieved source. You STOP when questions are
answered or budget is exhausted.

Working state:
  item: {{item}}
  open_questions: {{questions}}
  gathered_facts: {{facts_so_far}}        # each with source ref
  working_analysis: {{draft_analysis}}
  remaining_token_budget: {{budget_left}}
  loop_depth: {{depth}} / cap {{depth_cap}}

Think step by step:
  1. Which open question is most important and still unanswered?
  2. What action (from ActionSpace) best advances it?
  3. If no useful action remains or budget low → STOP.

Output (strict JSON):
{
  "action": str,                 # one of ActionSpace
  "target": str,                 # query/url/entity for the action
  "thought": str,                # CoT, ≤120 words
  "stop": bool
}
```

After each `RETRIEVE_*`, a **reader** sub-prompt extracts facts + claims from the
retrieved text and appends to `gathered_facts`. After `SYNTHESIZE`/`STOP`, a
**writer** sub-prompt emits the final `Analysis` (adaptive schema) including the
two-altitude block (beginner analogy + expert mechanism) and the `Claim[]` list.

**Adaptive analysis schema (one schema, `type` passed in prompt — §11.3):**

```
Analysis {
  item_id, analyzer_version,
  type: "paper"|"model_release"|"product"|"benchmark"|"industry"|"community",
  headline: str,
  summary: str,                       # expert altitude
  analogy: str,                       # beginner altitude
  mechanism: str,                     # expert mechanism
  significance: str,                  # why it matters
  type_specific: dict,                # free blob: numbers, benchmarks, lineage…
  claims: Claim[],                    # extracted, pre-verification
  entities: EntityRef[],              # for KG
  confidence: float
}
Claim {
  id, text, claim_type:
    "performance"|"capability"|"release"|"comparison"|"timeline"|"opinion",
  entities: str[], sources: SourceRef[], confidence: float,
  status: "UNVERIFIED"                # set by Verification
}
```

**Tools.** Targeted collectors (same adapters as Discovery, but *query-driven*),
`bus.recall_similar` (RAG within corpus), `bus.traverse_kg` (rivals/lineage),
`bus.recall_reports` (continuity: "we covered the preprint 3 months ago"),
LLM `research` role (controller + reader + writer).

**Memory.** Reads corpus/Qdrant/KG/reports. Writes Analysis + claims + KG
entities/relations + vectors (already embedded at ingest).

**Stopping (any triggers stop):**
- All `questions` answered, OR
- `loop_depth` ≥ `loop_depth_cap`, OR
- `loop_breadth` (retrievals this depth) ≥ `loop_breadth_cap`, OR
- `token_budget` exhausted, OR
- `STOP` action chosen.
On stop → emit partial-if-needed analysis with `gaps`.

**Metrics (Depth).** `avg_claims_per_deep_item`, `two_altitude_present_rate`,
`source_per_claim_avg`, `questions_answered_rate`, `gaps_rate` (track, don't punish —
partial tolerance), `kg_edges_added`.

**Failure/degradation.** A failed retrieval → log, add to `gaps`, continue. A failed
LLM call mid-loop → return the best analysis gathered so far (partial). Never blocks
the report.

---

### 5.5 Verification Agent

**Role.** The skeptic. Triangulates every claim against independent sources and
labels it. The headline **Accuracy + Trust** differentiator vs Perplexity (§12.5).

**Responsibilities.** For each `Claim` in each analysis: retrieve independent
items/sources via Qdrant + KG; classify `CORROBORATED | CONFLICTING |
SINGLE_SOURCE | UNVERIFIABLE`; attach source refs + confidence; flag high-severity
conflicts for escalation (§4.4).

**Inputs.** `Analysis[]` (with `Claim[]`), `RunContext`.

**Outputs.** `VerifiedAnalysis[]` (claims now carry `status` + verification refs);
`escalation` signals for high-severity conflicts.

**Reasoning.** *Claim triangulation* (§3). For each claim, the verifier retrieves
items that are *independent* of the claim's own sources (different publisher/source
type) and judges agreement.

**Prompt (verifier — per claim batch):**

```
Role: Skeptical fact-checker. You do NOT trust the analysis; you corroborate it.
You NEVER mark a claim CORROBORATED without an independent source.
You NEVER invent corroboration.

Claim to verify: {{claim}}
Original sources: {{claim.sources}}
Independent candidates retrieved: {{candidates}}   # from Qdrant+KG, diff source

Rules:
  - CORROBORATED: ≥1 independent candidate agrees, with a citeable source.
  - CONFLICTING: ≥1 independent candidate contradicts; report both sides + refs.
  - SINGLE_SOURCE: only the original source exists; no independent confirmation.
  - UNVERIFIABLE: claim is opinion/timeline-future or no retrievable evidence.
  - If a CONFLICTING or UNVERIFIABLE claim is high-severity (performance/comparison
    central to the item's significance), set escalate=true.

Output (strict JSON, extra="forbid"):
{
  "claim_id": str,
  "status": str,
  "confidence": float,
  "verification_sources": [SourceRef],
  "note": str,                # what the independent source says
  "escalate": bool
}
```

**Tools.** `bus.recall_similar` (independent candidates, filtered to exclude the
claim's own sources), `bus.traverse_kg` (lineage that supports/conflicts),
LLM `verify` role.

**Memory.** Reads corpus/Qdrant/KG. Writes verification status *back into* the
`Analysis.claims` (mutates the stored analysis; idempotent by version).

**Stopping.** All claims in all analyses checked, OR verification token budget
exhausted (remaining claims stay `UNVERIFIED`→treated as `SINGLE_SOURCE` in report,
flagged), OR per-claim retrieval `top_k` exhausted with no independent candidate.

**Metrics (Accuracy/Trust).** `corroborated_rate`, `conflicting_rate`,
`single_source_flagged_rate`, `unverifiable_rate`, `citation_presence_rate`
(claims with ≥1 source ref), `escalations_raised`, `escalations_resolved`
(via §4.4 loop).

**Failure/degradation.** Retrieval empty → claim marked `SINGLE_SOURCE` (honest, not
fatal). LLM fail → leave `UNVERIFIED`, report flags it.

---

### 5.6 Trend Agent

**Role.** The historian. Computes deltas and trajectories; reasons over the KG for
lineage/rivalry narratives. Raises **Synthesis** ("compare with previous work").

**Responsibilities.** Compute daily/weekly deltas (rising/fading topics) from prior
`TrendSnapshot`; narrate trajectories using KG edges (`succeeds`, `competes_with`,
`beats`); emit `TrendReport`.

**Inputs.** Current corpus (Items + Analyses), prior `TrendSnapshot[]`, KG, `profile`
(window).

**Outputs.** `TrendReport` (rising/fading topics, trajectories, novelty list) +
new `TrendSnapshot` committed.

**Reasoning.** Deltas are **SQL** (P2). *Narration* of trajectories is LLM (CoT):
"Model X, which beat Y last month, is now succeeded by Z." KG edges supply the
relationships; the LLM writes the prose, grounded in those edges (no invented edges).

**Prompt (trend narrator — bounded):**

```
Role: Trend analyst. Explain WHAT is rising/fading and WHY, using only the
provided deltas and KG relationships. Do not invent relationships.

Deltas (this window vs last): {{deltas}}
KG relationships in play: {{kg_edges}}
Prior trajectory notes: {{prior_trajectory}}

Output (strict JSON):
{
  "rising": [{"topic": str, "delta": float, "why": str}],
  "fading": [{"topic": str, "delta": float, "why": str}],
  "trajectories": [{"narrative": str, "entities": [str]}],  # KG-grounded
  "novelty": [str]            # first_seen this window
}
```

**Tools.** `bus.recall_trends` (prior), `bus.traverse_kg`, `bus.recall_items`
(window), LLM `trend` role.

**Memory.** Reads trends + KG + items. Writes new `TrendSnapshot` + KG edges
(lineage discovered during narration, conservative).

**Stopping.** All windows computed + narration emitted, OR trend token budget hit
(deltas still emitted; narration truncated, flagged).

**Metrics (Synthesis).** `rising_count`, `fading_count`, `kg_grounded_trajectories`,
`novelty_captured`, `delta_computation_cost` (should be ~0 — SQL).

**Failure/degradation.** No prior snapshot (first run) → deltas empty, narrate
"baseline established"; not fatal.

---

### 5.7 Writer Agent (RAG-grounded)

**Role.** The author. Assembles the 16 sections from verified analyses, clusters,
trends, and **retrieved historical context**. Raises **Synthesis + Usefulness +
Trust**.

**Responsibilities.** Retrieve continuity context (past reports/papers via RAG);
for each of the 16 section renderers, ground claims to verified analyses, write with
two-altitude where deep-dive, bind citations; assemble `DraftReport`.

**Inputs.** `RunContext` + `VerifiedAnalysis[]` + `TrendReport` + clusters (from a
light clustering step) + `profile.sections`.

**Outputs.** `DraftReport` (`ReportModel`: structured sections with claims+citations).

**Reasoning.** *RAG grounding* (§3). Before drafting, the Writer retrieves, per
section, top-k historical context (prior reports covering the same entity/cluster,
prior papers, prior benchmark rows). It then writes each section binding every
non-trivial claim to a `SourceRef` and every deep-dive to its two-altitude block.
The Writer **cannot** upgrade a `SINGLE_SOURCE`/`CONFLICTING` claim's confidence
(P7) — it must phrase it as "reported by X; independent confirmation pending."

**Prompt (section author — per section, micro-prompt; the 16 renderers each supply
their own title/shape):**

```
Role: Senior AI-industry report author. Write the "{{section_title}}" section.
Every factual claim MUST cite a SourceRef from the provided material.
For DEEP items, include BOTH altitudes: a one-line analogy for a smart
non-specialist, then the expert mechanism.

Provided (verified) material: {{verified_analyses_for_section}}
Continuity context (RAG): {{historical_context}}
Verification flags to honor: {{flags}}   # SINGLE_SOURCE/CONFLICTING → hedge

Rules:
  - No claim without a citation.
  - Honor verification status: hedge unverified/conflicting claims explicitly.
  - Use tables for benchmark numbers; callouts for conflicts; selective Mermaid
    only where it clarifies a relationship (else plain text).
  - Two-altitude required for any item tagged DEEP/EXHAUSTIVE.

Output: section markdown + a claims_manifest [{text, source_ref, status}].
```

**Tools.** `bus.recall_reports` (RAG continuity), `bus.recall_similar` (prior
papers/items), `bus.traverse_kg` (relationships to surface), LLM `markdown` role.

**Memory.** Reads everything via bus. Writes nothing persistent yet (draft is
in-memory; Archive persists it).

**Stopping.** All enabled sections drafted, OR writer token budget hit (emit drafted
sections + `partial` flag listing unwritten sections).

**Metrics (Usefulness/Trust).** `sections_complete`, `citation_rate`,
`two_altitude_in_deep_sections`, `hedged_unverified_rate` (correct hedging),
`continuity_references` (RAG hits actually used), `mermaid_overuse` (penalize
forced diagrams).

**Failure/degradation.** RAG empty (early days) → write without continuity refs,
flag. LLM fail on a section → skip section, flag in Coverage note.

---

### 5.8 Critic Agent

**Role.** The editor. Judges the draft against the §11.1 rubric and returns
*structured* fixes. Raises **Accuracy + Usefulness + structure** (§12.6).

**Responsibilities.** Score the draft on the 6 rubric dimensions; emit a strict
`CritiqueReport` of fixes; optionally demand a source for an unsupported claim
(which can trigger a Writer→(Research) re-grounding, bounded).

**Inputs.** `DraftReport` + source `VerifiedAnalysis[]` (to check claims against
evidence).

**Outputs.** `CritiqueReport` = `list[Fix]` where
`Fix = {section, issue_type, severity, instruction, requires_source}`.

**Prompt (critic):**

```
Role: Ruthless senior editor. Evaluate the draft ONLY against these dimensions:
  Coverage, Accuracy/Verification, Depth, Synthesis, Usefulness, Trust/Provenance.
For each problem, output a structured fix — not prose.

Draft: {{draft}}
Source evidence (verified analyses): {{evidence}}

Issue types (closed set):
  WEAK_EXPLANATION, UNSUPPORTED_CLAIM, MISSING_CONTEXT,
  POOR_STRUCTURE, UNHEDGED_CONFLICT, MISSING_CITATION,
  SHALLOW_DEPTH, REDUNDANT

Severity: BLOCKER (must fix) | MAJOR | MINOR.
If a claim has no source and isn't flagged SINGLE_SOURCE, set
requires_source=true and severity=BLOCKER.

Output (strict JSON, extra="forbid"):
{
  "scores": {"coverage":0-10, "accuracy":0-10, "depth":0-10,
             "synthesis":0-10, "usefulness":0-10, "trust":0-10},
  "fixes": [{"section": str, "issue_type": str, "severity": str,
             "instruction": str, "requires_source": bool}]
}
```

**Tools.** `bus.recall_*` (to verify a `requires_source` claim if needed),
LLM `critic` role (strong reasoning model).

**Memory.** Reads draft + evidence via bus/context. Writes nothing persistent.

**Stopping.** Critique emitted with valid schema, OR critic budget hit (emit
partial scores + found fixes). Max **2** critique passes (§4.4): after the Writer
rewrites, the Critic re-checks once; if BLOCKERs remain after pass 2, the report
ships with a `known_issues` note (partial tolerance, never blocks).

**Metrics (Accuracy/Usefulness).** `blocker_count`, `major_count`, `minor_count`,
`fix_acceptance_rate` (after rewrite, how many fixes resolved), `rubric_scores`
(the 6 numbers — these seed the global quality score §7).

**Failure/degradation.** Malformed critique (schema error) → caught by
`extra="forbid"` validation; retry once; if still bad, skip critique (report ships
un-critiqued, flagged).

---

### 5.9 Markdown Renderer (light cognition)

**Role.** Formats the `FinalReportModel` to canonical Markdown (+ Obsidian wikilink
variant). Raises **Usefulness/Trust** via clean presentation.

**Responsibilities.** Walk the structured `ReportModel` → Markdown (tables, callouts,
selective Mermaid, citations, Obsidian wikilinks). No LLM.

**Inputs.** `FinalReportModel` (post-rewrite).

**Outputs.** Markdown string (+ variant for Obsidian) → `Sink(s)`.

**Reasoning.** Pure formatting; the *structure* was decided by the Writer/Critic.
Honors "Mermaid only where it clarifies" (a flag set during writing).

**Prompt.** None.

**Tools.** `Renderer` + `Sink` protocols (§12.11). Markdown canonical; Obsidian =
Markdown with wikilinks; HTML/PDF = md→html→pdf later.

**Memory.** None (reads the in-memory model).

**Stopping.** All sections rendered.

**Metrics.** `render_errors`, `citation_link_integrity` (every `[n]` resolves).

---

### 5.10 Archive Agent (light cognition)

**Role.** Persists the report and updates the memory stores so tomorrow is smarter.
Raises **Synthesis/Trust** long-term (memory closure).

**Responsibilities.** Commit `Report` row + run manifest; finalize KG edges; commit
`TrendSnapshot`; write the **Coverage & Method** note (which sources ran, what
failed, what was partial).

**Inputs.** `FinalReportModel`, run manifest, all provenance blocks.

**Outputs.** Persisted report + updated memory; Coverage note appended.

**Reasoning.** None (deterministic assembly of the Coverage note from collected
provenance — this is nearly free Trust).

**Prompt.** None.

**Tools.** `bus.commit_report`, `bus.assert_relation` (finalize), `bus.commit_trend`.

**Memory.** Writes Report + KG + Trend + manifest.

**Stopping.** All commits succeed; on SQLite failure, retry once, then write report
file to disk regardless (never lose the report).

**Metrics.** `kg_edges_finalized`, `coverage_note_completeness`, `commit_failures`.

---

## 6. Cross-Agent Coordination: the InvestigationPlan

The `InvestigationPlan` is the central coordination artifact produced by Planning
and consumed by Research/Verification. It is what makes the agents *collaborate*
rather than run blind.

### 6.1 Depth tiers

| Tier | Trigger | What happens | Budget weight |
|---|---|---|---|
| **SKIM** | low rank / already-covered | summary line only, no analysis | ~0 LLM |
| **STANDARD** | solid item | typed analysis + verification | 1× |
| **DEEP** | high rank OR high novelty | research loops + RAG + verification | 3–5× |
| **EXHAUSTIVE** | deep_dive profile / single top item | max loops, full RAG, lineage | 8×+ |

### 6.2 `InvestigationTask` schema

```
InvestigationTask {
  item_id: str
  tier: "SKIM"|"STANDARD"|"DEEP"|"EXHAUSTIVE"
  questions: list[str]          # research sub-questions (DEEP/EXHAUSTIVE)
  token_budget: int             # allocated by Planning (§6.3)
  loop_depth_cap: int           # e.g. 3 for DEEP, 5 for EXHAUSTIVE
  loop_breadth_cap: int         # max retrievals per depth (e.g. 4)
}
```

### 6.3 Budget allocation (top-down)

Planning receives `profile.budget_tokens`. It allocates:
1. Fixed reserves: Discovery+Ingest (negligible), Trend (SQL-cheap), Writer
   (proportional to `top_k`), Critic (2 passes, capped).
2. Remaining → Research pool. Sort items by heuristic rank; assign DEEP to top-N
   until the Research pool is exhausted; rest STANDARD; bottom SKIM.
3. If `research_loops: false` (light profile), force all items to STANDARD/SKIM and
   zero the Research pool.

This guarantees the run never exceeds its token budget (P5) while spending the
marginal LLM dollar where it most raises Depth (DEEP items).

### 6.4 Example (daily profile, top_k=25, budget=2.4M tokens)

```
rank #1  (novel paper, high novelty)  → DEEP,  questions=[primary src, benchmarks, rivals], budget 180k
rank #2  (major model release)        → DEEP,  questions=[weights, license, rivals],        budget 180k
rank #3..8 (strong items)             → DEEP/STANDARD mix, 90k each
rank #9..25                           → STANDARD, 30k each
rest                                   → SKIM (no analysis)
TOTAL planned ≈ 2.35M ≤ 2.4M budget.
```

---

## 7. Evaluation & the Quality Loop

### 7.1 Per-agent metrics (operational)

Each agent emits the metrics in §5. They are written to the run manifest and feed
(1) the Coverage & Method note and (2) the global quality score.

### 7.2 Report-level quality score (rubric-scored)

A single `QualityScore` is computed per report, each dimension 0–10:

| Dimension | Computed from |
|---|---|
| Coverage | source_type_diversity + items_analyzed + blind_spot check |
| Accuracy | corroborated_rate − conflicting_unhedged − missing_citation |
| Depth | two_altitude_rate + avg_claims_deep + shallow_depth penalties |
| Synthesis | cluster coherence + trend deltas + continuity_references |
| Usefulness | takeaway density + engineering-implication presence |
| Trust | provenance labeling + hedged_unverified_rate + citation integrity |

`QualityScore = mean(dims)`. This is the number the Phase 8 loop optimizes.

### 7.3 The Phase 8 quality loop (Hermes vs Perplexity)

The report only improves if measured (§11.5). Protocol:
1. On a calibration day, run **both** Hermes and "Perplexity: today's AI news" on
   the same input date.
2. Blind-eval the two outputs on the 6 dimensions (LLM judge or human).
3. Diff: where Hermes loses (e.g., weaker verification, thinner depth), file a
   *prompt/selection* change (not an architecture change).
4. Re-run; track `QualityScore` trend over calibration days.
5. Gate: a change ships only if it raises `QualityScore` without raising cost/run
   time beyond profile bounds.

This loop is the optimization engine. It never justifies elegance-infra — only
prompt/selection tuning that moves the score.

### 7.4 Calibration tracking

Store per-run `QualityScore` + per-dimension in the manifest; plot trend. A falling
dimension after a change → revert. This is how Hermes "remembers" what works.

---

## 8. Cost & Budget Governance

- **Global budget** comes from `profile.budget_tokens`. The `BudgetLedger` in
  `RunContext` deducts per agent call; agents check `budget_left` before each LLM
  call and stop when ≤0 (P5).
- **Cost safety:** the LLM router keeps a token counter (§11.2) so the agent stays
  alive; if a run approaches the hard ceiling, low-priority agents (Writer polish,
  Critic pass 2) are sacrificed first; Research loops tighten.
- **Quality-vs-cost knobs = report profiles** (§12.10): `daily` (balanced), `weekly`
  (deep, higher top_k + budget), `deep_dive` (exhaustive, 1 item), `company_profile`
  / `trend_report` (focused). No pipeline code per type — only profile params.
- **Fallback across models** (§12.3 router) ensures the report is always written even
  if the primary model is down — reliability is a quality prerequisite.

---

## 9. Open Questions for Cognition Layer

1. **Critic model strength.** Should the Critic use the strongest available model
   (best critique) or a mid model (cost)? Recommend strongest — it's 2 passes,
   bounded, and directly sets published quality.
2. **Verification escalation bound.** One re-loop per conflicting claim, or a global
   cap on escalations per run? Recommend global cap (e.g., ≤3) to protect budget.
3. **Two-pass Critic always, or only when BLOCKERs exist?** Recommend: always run
   pass 1; run pass 2 only if pass 1 had BLOCKERs/MAJORs (saves a pass on clean drafts).
4. **RAG top-k per section.** Default 5 historical + 5 corpus; tune via Phase 8.
5. **KG extraction timing.** Extract entities during Research (rich context) vs a
   dedicated pass post-analysis. Recommend during Research (the analysis already has
   the entities in hand) + a Trend-Agent consolidation pass.
6. **Confidence calibration.** Should confidence be model-logit-derived or
   LLM-self-reported? Recommend LLM-self-reported + source-count as a sanity floor
   (cheap, good enough; revisit only if calibration metrics look off).

---

## 10. Summary — how the cognition layer serves the rubric

| Rubric dim | Primary agent(s) | Mechanism |
|---|---|---|
| **Coverage** | Discovery, Planning | 30+ sources, fault-isolated; coverage-balanced tiering |
| **Accuracy/Verification** | Verification (+ Research escalation) | claim triangulation, independent-source labeling |
| **Depth** | Research | bounded ReAct loops, two-altitude, RAG |
| **Synthesis** | Trend, Writer, Planning | clusters, deltas, KG trajectories, continuity RAG |
| **Usefulness** | Writer, Planning, Critic | takeaways, engineering implications, rubric critique |
| **Trust/Provenance** | all claim-emitters, Archive | provenance on every claim, Coverage & Method note |

The cognition layer is deliberately **not** a framework: it is ten focused modules
sharing a `RunContext`, a `MemoryBus`, a `Handoff` protocol, and one bounded
Critic→Rewrite (plus one bounded Verification→Research) loop — each mechanism mapped
to a quality dimension, each bounded by budget, each partial-tolerant. That is what
lets Hermes maximize report quality without becoming elegance-infra.
