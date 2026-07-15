# AI NEWS MONTHLY RETROSPECTIVE

**Cadence:** monthly retrospective, 30-day lookback window.

Autonomous monthly retrospective. Synthesizes the past 30 days into a
narrative: what happened, why it mattered, how it changed the industry,
and what comes next. Reads like a hybrid of the Stanford AI Index and
top-tier equity research.

# Research Instructions

Synthesize hundreds of signals into a single retrospective. For every
factual claim, cite the exact source URL with the token `[src:URL]` right
after the claim. Prefer primary sources; corroborate important claims
using multiple reputable sources.

## Official Sources

_Why these sources:_ the labs, chip vendors, and platform companies that
publish first-party research, model cards, and benchmark results.

- OpenAI
- Anthropic
- Google DeepMind
- Google AI
- Microsoft AI
- Meta AI
- xAI
- NVIDIA
- AMD
- Intel
- Apple ML Research
- Amazon AWS AI
- IBM Research
- Hugging Face
- Mistral AI
- DeepSeek
- Alibaba Qwen
- Moonshot AI
- Zhipu AI
- Perplexity
- Groq
- Cerebras
- Databricks
- Cohere

## Research Sources

_Why these sources:_ open-access archives and venue proceedings where new
architectures and benchmark results surface first.

- arXiv
- Semantic Scholar
- Papers With Code
- Nature
- Science
- NeurIPS
- ICML
- ICLR
- CVPR

## Trusted News Sources

_Why these sources:_ newsrooms with track records of accurate tech and
business reporting, plus the financial press that covers funding events.

- Reuters
- Bloomberg
- Financial Times
- The Information
- MIT Technology Review
- TechCrunch
- IEEE Spectrum
- VentureBeat

## Community Intelligence

_Why these sources:_ developer communities that surface adoption patterns,
benchmark skepticism, and hidden trends before the press does. Use for
sentiment, never as fact.

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

1. **Compare this month against the prior month** explicitly. State the
   delta: which labs gained capability, which lost ground, which shipped
   nothing. Render a Markdown comparison table for the top 3-5 frontier
   models released or updated this month, with columns for Model,
   Developer, Context, Reasoning, Coding, Pricing, Release date.
2. **Rank** funding rounds by capital deployed, not chronology. Render a
   Markdown table of the largest rounds with columns for Company, Round,
   Size, Lead investor, Valuation, Date.
3. **Quantify** benchmark deltas with a Markdown comparison table for
   GPQA, AIME, SWE-Bench, MMLU, MMMU, with the score and the
   confidence interval where the source provides one. Discuss overfitting
   and benchmark contamination.
4. **Contrast** this month's moves with the same month one year ago. State
   the trajectory explicitly.
5. **Surface contradictions** between labs and external evaluators
   (especially on capability claims and benchmark numbers). Do not
   silently pick a side.
6. **Distinguish** facts, analysis, estimates, rumors, and community
   sentiment in every paragraph.

# Report Structure

_(use 8-12 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- biggest breakthroughs of the month
- biggest disappointments
- largest industry shifts
- **comparison with the prior month** — state the delta, do not just list

## 2. Month Timeline
- major model releases, research breakthroughs, and product launches
- funding, acquisitions, and regulation milestones
- explain why each mattered

## 3. Frontier & Infrastructure
- model releases: architecture, context, reasoning, coding, pricing
- chips, systems, serving frameworks, and supply signals
- _→ render as Markdown comparison table for top models (Model,
  Developer, Context, Reasoning, Coding, Pricing, Release date)_
- _→ render a second Markdown table for chips/hardware if the section
  has in-window chip data (Chip, Vendor, Process node, Memory,
  Notable use)_

## 4. Research Breakthroughs
- reasoning, inference scaling, MoE, memory, long-context
- RAG, synthetic data, RL, alignment, interpretability
- efficient training methods
- for each paper: problem, method, innovation, impact
- _→ render as Markdown table for top papers by impact (Paper,
  Problem, Method, Innovation, Impact)_

## 5. AI Agents & Open Source
- coding agents, agent platforms, MCP/A2A ecosystem
- open-weight releases and ecosystem traction
- _→ render as Markdown table for leading agent platforms (Platform,
  Developer, Modalities, MCP/A2A, Notable capability, Adoption)_

## 6. Funding, M&A & Business
- largest investments and acquisitions
- new unicorns, IPOs, market consolidation
- _→ render as Markdown comparison table for largest rounds (Company,
  Round, Size, Lead investor, Valuation, Date)_

## 7. Regulation & Policy
- United States, EU, UK, China, India
- AI safety, copyright, privacy, open-source policy

## 8. Enterprise & Industry Adoption
- healthcare, finance, legal, defense, software engineering
- measurable productivity where available

## 9. Benchmarks & Capability
- GPQA, AIME, SWE-Bench, MMLU, MMMU
- discuss limitations and overfitting
- _→ render as Markdown comparison table for benchmark results (Model,
  Benchmark, Score, Date, Source)_

## 10. Predictions & Watchlist
- next models, research directions, hardware
- agent evolution, regulatory outlook
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- Month timeline
- **Markdown comparison table for top frontier models (Model, Developer, Context, Reasoning, Coding, Pricing, Release date)**
- **Markdown comparison table for chips/hardware when in-window chip data exists (Chip, Vendor, Process node, Memory, Notable use)**
- **Markdown comparison table for top research papers by impact (Paper, Problem, Method, Innovation, Impact)**
- **Markdown comparison table for leading agent platforms (Platform, Developer, Modalities, MCP/A2A, Notable capability, Adoption)**
- **Markdown comparison table for largest funding rounds (Company, Round, Size, Lead investor, Valuation, Date)**
- **Markdown comparison table for benchmark results (Model, Benchmark, Score, Date, Source)**
- Key statistics throughout
- Strategic conclusions

# Output Quality Requirements

- Synthesize rather than merely summarize.
- Explain significance, not just chronology.
- Prefer primary sources over secondary reporting.
- Corroborate important claims using multiple reputable sources.
- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate facts, analysis, estimates, rumors, and community sentiment.
- Include publication dates for time-sensitive information.
- Use comparison tables for models, hardware, and funding — one table per topic.
- Quantify adoption, funding, performance, pricing, and market impact.
- Flag disagreements between sources when they exist.
- Produce a polished report for executives, researchers, and engineers.
- State the ranking criterion whenever a section ranks items.
- Compare this month against the prior month explicitly.
