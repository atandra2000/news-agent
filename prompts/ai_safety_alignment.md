# AI SAFETY, ALIGNMENT & INTERPRETABILITY BRIEF

**Cadence:** weekly, focused on safety and governance.

Autonomous brief on the safety and alignment frontier: capability
evaluations, interpretability research, red-team findings, and
governance-relevant incidents. Best run weekly.

# Research Instructions

For every factual claim, cite the exact source URL with the token
`[src:URL]` immediately after the claim. Prefer primary papers,
official evals, agency reports, and lab safety statements over
press coverage.

## Official Sources

_Why these sources:_ the labs, institutes, and standards bodies that
publish first-party safety evaluations, red-team findings, and
governance frameworks.

- OpenAI Safety
- Anthropic Safety
- Google DeepMind Safety
- Apollo Research
- METR (Model Evaluation & Threat Research)
- US AI Safety Institute
- UK AI Safety Institute
- US NIST AI
- US White House OSTP
- EU AI Office
- China CAC
- Partnership on AI
- CAIS (Center for AI Safety)
- MLCommons
- IEEE Standards Association

## Research Sources

_Why these sources:_ open-access archives and venues where alignment
and interpretability research is canonical.

- arXiv (cs.AI, cs.LG, cs.CL)
- Semantic Scholar
- Papers With Code
- Hugging Face
- Distill
- Alignment Forum
- LessWrong

## Trusted News Sources

_Why these sources:_ newsrooms with track records on safety and
governance reporting.

- MIT Technology Review
- The Information
- Reuters
- TechCrunch
- IEEE Spectrum
- VentureBeat
- Time AI
- Semafor

## Community Intelligence

_Why these sources:_ practitioner communities that surface
reproduction attempts, benchmark skepticism, and incident
discussion. Use for sentiment, never as fact.

- Hacker News
- r/MachineLearning
- r/singularity
- LessWrong
- Alignment Forum
- X (safety researchers)

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A list
of incidents or papers is not a safety brief.

1. **Distinguish research, incident, and policy cleanly.** Each
   section should declare which of the three it covers, not blend
   them.
2. **Rank evaluations by what they measure, not by leaderboard
   position.** State the eval's scope, what it cannot detect, and
   the eval-set staleness risk.
3. **Compare evaluations on a consistent axis** (capability tested,
   threshold, red-team methodology, score). Render a Markdown
   comparison table for in-scope evaluations.
4. **Quantify** every claim: eval scores, red-team success rates,
   capability thresholds, parameter counts, dates, fine-tuning
   data sizes.
5. **Contrast** this period's safety work with the prior period —
   what shifted, what regressed, what new threat models emerged.
6. **Surface disagreements between labs and external evaluators**
   explicitly. State the disagreement, do not pick a side
   silently.
7. **Distinguish** confirmed incidents, reported-but-unconfirmed
   incidents, and disclosed-but-debated incidents.

# Report Structure

_(use 8-12 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining safety and alignment shifts this period
- highest-impact evaluations and incidents
- one-sentence verdict

## 2. Capability Evaluations
- new benchmarks (HLE, FrontierMath, SWE-Bench, MASK, MLE-Bench)
- scores, limitations, and overfitting analysis
- capability threshold crossings
- _→ render as Markdown comparison table (Eval, Capability, Score,
  Threshold, Date)_

## 3. Alignment Research
- RLHF, RLAIF, Constitutional AI, debate, weak-to-strong
- scalable oversight and amplification
- for each paper: problem, method, innovation, impact

## 4. Interpretability
- mechanistic interpretability, probing, sparse autoencoders
- representation engineering, activation patching
- notable findings and replication status

## 5. Red-Teaming & Jailbreaks
- novel attack vectors and defenses
- universal jailbreaks, prompt injection, agent hijacks
- disclosure norms and responsible reporting

## 6. Safety Incidents
- misuse cases, near-misses, and confirmed harms
- lab response and disclosure
- regulatory or legal consequences

## 7. Governance & Standards
- frontier-model obligations and reporting
- third-party eval access and red-team rights
- compute thresholds, whistleblower protections

## 8. Predictions & Watchlist
- next eval releases, alignment milestones
- regulatory deadlines
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- **Markdown comparison table for evaluations (Eval, Capability, Score, Threshold, Date)**
- Incident log
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified facts from analysis and community sentiment.
- Prefer primary sources; state when only press/social evidence exists.
- Quantify: eval scores, red-team success rates, parameter counts, dates.
- Use comparison tables for evaluations and incidents.
- Include publication dates for time-sensitive claims.
- Distinguish research from incident from policy cleanly.
- Flag disagreements between labs and external evaluators when they exist.
- State the ranking criterion whenever a section ranks items.
- Distinguish confirmed, reported-but-unconfirmed, and disclosed-but-debated incidents explicitly.
