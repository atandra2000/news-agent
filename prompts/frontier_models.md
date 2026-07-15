# FRONTIER AI MODELS — FOCUSED BRIEF

**Cadence:** weekly, deep comparison-first report.

Autonomous focused brief on frontier model releases and capability shifts.
Best run weekly for a deep, comparison-first report.

# Research Instructions

For every factual claim, cite the exact source URL with the token
`[src:URL]` immediately after the claim. Prefer official model cards,
technical reports, and benchmark repositories over press coverage.

## Official Sources

_Why these sources:_ the labs and organizations that publish first-party
model cards and benchmark results.

- OpenAI
- Anthropic
- Google DeepMind
- Meta AI
- xAI
- Mistral AI
- DeepSeek
- Alibaba Qwen
- Moonshot AI
- Zhipu AI
- MiniMax
- Cohere
- Perplexity

## Research Sources

_Why these sources:_ open-access archives and leaderboards where new
architectures and benchmark results surface first.

- arXiv
- Papers With Code
- Hugging Face models
- Semantic Scholar

## Trusted News Sources

_Why these sources:_ newsrooms with track records of accurate tech
reporting and access to off-record industry sources.

- The Information
- MIT Technology Review
- TechCrunch
- VentureBeat
- Reuters

## Community Intelligence

_Why these sources:_ developer communities that surface benchmark
skepticism and real adoption signal. Use for sentiment, never as fact.

- Hacker News
- r/LocalLLaMA
- r/singularity
- Hugging Face Trending

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A list
of model releases is not a frontier-model brief.

1. **Rank models by capability on the user's task**, not by release
   date. State the ranking criterion explicitly.
2. **Compare every model on a consistent axis** (context, reasoning,
   coding, math, multimodal, agent, pricing). Render a Markdown
   comparison table for the top models in scope.
3. **Quantify** every claim: parameter count, context length, pricing
   per million tokens, benchmark scores with confidence intervals
   where the source provides them.
4. **Contrast** closed-weight and open-weight frontier — how close is
   the open-weight frontier to the proprietary one? Render a Markdown
   table.
5. **Discuss benchmark limitations**: contamination, overfitting to
   public test sets, eval set staleness. Do not present benchmark
   scores as capability claims without caveat.
6. **Distinguish** vendor demos, third-party evaluations, and
   community reproductions.

# Report Structure

_(use 8-15 sources per section; prefer 3 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining capability shifts this period
- who gained or lost ground
- one-sentence verdict

## 2. Model Comparison Matrix
- every major model released or updated
- release date, developer, architecture, context length
- reasoning, coding, math, multimodal, agent capability
- pricing and benchmark standing
- _→ render as Markdown comparison table (Model, Developer, Context,
  Reasoning, Coding, Math, Multimodal, Agent, Pricing, Release date)_

## 3. Deep Dives
- the 2-3 most consequential models in scope
- for each: architecture and training approach, innovations,
  limitations, reception, enterprise adoption
- one model per subsection

## 4. Benchmark Analysis
- GPQA, AIME, SWE-Bench, MMLU, MMMU
- discuss limitations and potential overfitting
- _→ render as Markdown comparison table (Model, GPQA, AIME,
  SWE-Bench, MMLU, MMMU, Date)_

## 5. Open-Weight Challengers
- DeepSeek, Qwen, Llama, Gemma, Mistral
- how close open-weight is to proprietary frontier
- pricing and adoption disruption
- _→ render as Markdown comparison table (Model, Developer,
  Parameters, Context, License, Top benchmark, Notable)_

## 6. Predictions
- next frontier releases
- capability trajectories
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- **Markdown comparison matrix of frontier models (Model, Developer, Context, Reasoning, Coding, Math, Multimodal, Agent, Pricing, Release date)**
- **Markdown comparison table of benchmark results (Model, GPQA, AIME, SWE-Bench, MMLU, MMMU, Date)**
- **Markdown comparison table of open-weight challengers (Model, Developer, Parameters, Context, License, Top benchmark, Notable)**
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified facts from analysis and community sentiment.
- Prefer primary sources; state when only social evidence exists.
- Quantify: parameter counts, context length, pricing, benchmark scores, dates.
- Use comparison tables for models and benchmarks — one table per topic.
- Include publication dates for time-sensitive claims.
- Synthesize and explain significance; do not merely list models.
- Flag disagreements between sources when they exist.
- State the ranking criterion whenever a section ranks items.
- Discuss benchmark contamination, overfitting, and eval-set staleness when reporting scores.
