# AI NEWS DAILY BRIEF

**Cadence:** daily, 24-hour lookback window.

Autonomous daily AI-news brief. Compact, high-signal, executive-readable.
Synthesize the day's most consequential AI developments; do not pad.

# Research Instructions

Prioritize primary and reputable sources. For every factual claim, cite
the exact source URL with the token `[src:URL]` immediately after the
claim.

## Official Sources

_Why these sources:_ the labs and platform companies that publish
first-party announcements and model updates.

- OpenAI
- Anthropic
- Google DeepMind
- Google AI
- Microsoft AI
- Meta AI
- xAI
- NVIDIA
- Mistral AI
- DeepSeek
- Alibaba Qwen
- Hugging Face
- Perplexity
- Cohere

## Research Sources

_Why these sources:_ open-access archives and leaderboards where
research output is canonical.

- arXiv
- Semantic Scholar
- Papers With Code
- Hugging Face models
- Nature
- Science

## Trusted News Sources

_Why these sources:_ newsrooms with track records of accurate tech
reporting.

- Reuters
- Bloomberg
- Financial Times
- The Information
- MIT Technology Review
- TechCrunch
- VentureBeat

## Community Intelligence

_Why these sources:_ developer communities that surface sentiment
and adoption signal. Use for sentiment, never as fact.

- Hacker News
- r/MachineLearning
- r/LocalLLaMA
- r/singularity
- GitHub Trending
- Hugging Face Trending

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A
daily brief is small; every sentence must add signal.

1. **Lead with significance, not chronology.** The executive summary
   should be 3-5 sentences of pure significance — no fluff, no
   throat-clearing.
2. **Compare to the prior day** where the source set allows — what
   shifted, what was incremental, what was retracted.
3. **Quantify** every claim: funding, benchmark scores, pricing,
   parameter counts, dates.
4. **Distinguish** verified facts from analysis, estimates, and
   community sentiment in every paragraph.
5. **Cite primary sources** — official posts, arXiv, model cards —
   and state when only social/community evidence exists.

# Report Structure

_(use 4-6 sources per section; prefer 1 official + 1 research + 1 news +
1 community)_

## 1. Executive Summary
- biggest developments today
- why they matter
- one-sentence takeaway

## 2. Model & Product Releases
- model launches and major updates
- pricing and access changes
- developer-facing capability shifts

## 3. Research & Breakthroughs
- notable papers and methods
- what is technically new
- why it matters for practitioners

## 4. Funding, M&A & Business
- raises, acquisitions, partnerships
- strategic moves by major labs
- market implications

## 5. Community & Ecosystem Signal
- developer sentiment
- trending repos and models
- hidden trends not yet in press

## 6. Benchmarks & Capability Moves
- new benchmark results
- notable capability gains or regressions
- comparison where multiple models are involved
- _→ render as Markdown comparison table when multiple models
  appear (Model, Benchmark, Score, Date)_

# Required Deliverables

- Executive summary
- Per-section analytical coverage
- **Markdown comparison table for benchmark moves when multiple models appear (Model, Benchmark, Score, Date)**
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified facts from analysis, estimates, and community sentiment.
- Prefer primary sources (official posts, arXiv, papers); state when only social/community evidence exists.
- Quantify: funding, benchmark scores, pricing, parameter counts, dates.
- Use a comparison table when multiple models or deals are compared.
- Include publication dates for time-sensitive claims.
- Synthesize and explain significance; do not merely list items.
- Flag disagreements between sources when they exist.
- Lead with significance, not chronology.
