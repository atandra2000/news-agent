# AI NEWS WEEKLY

**Cadence:** weekly, 7-day lookback window.

Autonomous weekly AI-news brief. Connects the past 7 days into trajectories,
compares model moves, and surfaces what actually shifted in the industry.

# Research Instructions

Synthesize the past 7 days into one coherent narrative. For every factual
claim, cite the exact source URL with the token `[src:URL]` right after the
claim. Prefer primary sources; secondary press only for context.

## Official Sources

_Why these sources:_ the labs and platform companies that publish
first-party announcements, model cards, and benchmark results.

- OpenAI
- Anthropic
- Google DeepMind
- Microsoft AI
- Meta AI
- xAI
- NVIDIA
- AMD
- Mistral AI
- DeepSeek
- Alibaba Qwen
- Moonshot AI
- Hugging Face
- Perplexity
- Cohere

## Research Sources

_Why these sources:_ open-access archives and venue proceedings where
research output is canonical.

- arXiv
- Semantic Scholar
- Papers With Code
- Hugging Face models & spaces
- NeurIPS
- ICML
- ICLR

## Trusted News Sources

_Why these sources:_ newsrooms with track records of accurate tech
reporting.

- Reuters
- Bloomberg
- Financial Times
- The Information
- MIT Technology Review
- TechCrunch
- IEEE Spectrum
- VentureBeat

## Community Intelligence

_Why these sources:_ developer communities that surface adoption
patterns, benchmark skepticism, and hidden trends. Use for sentiment,
never as fact.

- Hacker News
- r/MachineLearning
- r/LocalLLaMA
- r/singularity
- GitHub Trending
- Hugging Face Trending
- Substack AI newsletters

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. Mere
chronology is not synthesis; the report must compare, rank, quantify,
and contrast.

1. **Compare this week against the prior week** explicitly. State the
   delta: which labs gained capability, which lost ground, which
   shipped nothing.
2. **Rank** items by impact, not by chronology. State the ranking
   criterion.
3. **Quantify** every claim: funding, benchmark scores, pricing,
   parameter counts, dates.
4. **Contrast** this week's moves with the same week one year ago.
   State the trajectory.
5. **Surface contradictions** between sources. Do not silently pick
   a side.
6. **Distinguish** facts, analysis, estimates, rumors, and community
   sentiment in every paragraph.
7. **Highlight trajectories and relationships** between stories, not
   isolated blurbs.

# Report Structure

_(use 6-10 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining themes of the week
- biggest breakthroughs and disappointments
- comparison with the prior week

## 2. Frontier Model Releases
- every major model release or update this week
- release date, developer, architecture, context, pricing
- comparison against competitors released in the same window
- _→ render as Markdown comparison table (Model, Developer,
  Context, Reasoning, Coding, Pricing, Release date)_

## 3. Research & Methods
- advances in reasoning, inference scaling, MoE, efficient training
- for each paper: problem, method, innovation, impact

## 4. Open-Source Ecosystem
- major open-weight releases and forks
- license terms, ecosystem traction, community adoption

## 5. AI Agents & Tooling
- coding agents and agent platforms
- MCP / A2A ecosystem, reliability, security, evaluation

## 6. Hardware & Serving
- chip announcements, rack-scale systems, inference frameworks
- pricing, availability, supply-chain signals

## 7. Funding, M&A & Markets
- largest rounds, acquisitions, strategic partnerships
- market consolidation and emerging vs declining players
- _→ render as Markdown comparison table (Company, Round, Size,
  Lead investor, Date)_

## 8. Community & Watchlist
- developer sentiment and production lessons
- trajectories worth watching into next week

# Required Deliverables

- Executive summary
- **Markdown comparison table for frontier model releases (Model, Developer, Context, Reasoning, Coding, Pricing, Release date)**
- **Markdown comparison table for funding rounds (Company, Round, Size, Lead investor, Date)**
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified facts from analysis, estimates, and community sentiment.
- Prefer primary sources; state when only social evidence exists.
- Quantify: funding, benchmark scores, pricing, parameter counts, dates.
- Use comparison tables for models and funding — one table per topic.
- Include publication dates for time-sensitive claims.
- Synthesize and explain significance; do not merely list items.
- Flag disagreements between sources when they exist.
- Highlight trajectories and relationships, not isolated blurbs.
- State the ranking criterion whenever a section ranks items.
- Compare this week against the prior week explicitly.
