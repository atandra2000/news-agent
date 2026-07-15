# AI RESEARCH & PAPERS BRIEF

**Cadence:** weekly, focused on research output.

Autonomous brief on the most consequential AI research of the period.
Best run weekly. Engineering-first, method-forward, low on hype.

# Research Instructions

For every factual claim, cite the exact source URL with the token
`[src:URL]` immediately after the claim. Prefer arXiv, papers,
and official technical reports over secondary coverage.

## Official Sources

_Why these sources:_ the labs and organizations that publish
first-party research.

- OpenAI
- Anthropic
- Google DeepMind
- Meta AI
- Microsoft Research
- xAI
- NVIDIA Research
- Mistral AI
- DeepSeek
- Alibaba Qwen
- Hugging Face

## Research Sources

_Why these sources:_ open-access archives and venue proceedings where
research output is canonical.

- arXiv
- Semantic Scholar
- Papers With Code
- Hugging Face papers
- Nature
- Science
- NeurIPS
- ICML
- ICLR
- CVPR
- EMNLP
- ACL

## Trusted News Sources

_Why these sources:_ newsrooms with track records on research
reporting.

- MIT Technology Review
- IEEE Spectrum
- TechCrunch
- VentureBeat

## Community Intelligence

_Why these sources:_ developer communities that surface reproduction
attempts, benchmark skepticism, and practical takeaways. Use for
sentiment, never as fact.

- Hacker News
- r/MachineLearning
- r/LocalLLaMA
- Hugging Face Trending
- GitHub Trending

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A list
of paper titles is not a research brief.

1. **Rank by impact, not by submission date or citation count alone.**
   State the ranking criterion (downstream adoption, replication
   success, code release, benchmark gain).
2. **For each paper, state the problem, method, innovation, and
   impact explicitly** — four distinct beats per paper, not one
   paragraph of summary.
3. **Compare methods on a consistent axis** (compute, data, training
   paradigm, eval). Render a Markdown table when the section
   discusses 3+ methods.
4. **Quantify** every claim: dataset sizes, parameter counts,
   benchmark deltas, training FLOPs, eval scores, dates.
5. **Contrast** this period's methods with the prior period's
   state-of-the-art — what changed, what was incremental, what was
   retracted.
6. **Surface reproductions and failures explicitly.** Cite the
   reproduction, not just the original paper.
7. **Distinguish** theoretical contributions, empirical contributions,
   and engineering contributions.

# Report Structure

_(use 8-12 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining research themes this period
- the 2-3 papers that matter most
- one-sentence verdict

## 2. Reasoning & Inference Scaling
- test-time compute, search, verification
- why it matters for capability
- for each paper: problem, method, innovation, impact

## 3. Architectures
- MoE, sparse models, state-space, hybrids
- memory and long-context methods
- for each paper: problem, method, innovation, impact

## 4. Training & Efficiency
- efficient training, quantization, distillation
- synthetic data and RL/RLHF/RLAIF
- for each paper: problem, method, innovation, impact

## 5. Multimodal & Generative
- vision-language, diffusion, audio, video
- unified generation methods
- for each paper: problem, method, innovation, impact

## 6. Alignment & Interpretability
- safety, probing, mechanistic interpretability
- evaluation and red-teaming
- for each paper: problem, method, innovation, impact

## 7. Embodied & Systems
- robotics, world models, simulation
- systems and serving research
- for each paper: problem, method, innovation, impact

## 8. Reproducibility & Community
- notable reproductions or failures
- open weights and code releases
- practitioner takeaways

## 9. Predictions
- next research directions
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- Per-paper method summaries (problem, method, innovation, impact)
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified facts from analysis and community sentiment.
- Prefer primary sources; state when only social evidence exists.
- Quantify: datasets, metrics, parameter counts, dates.
- For each paper give problem, method, innovation, impact — four distinct beats.
- Synthesize and explain significance; do not merely list titles.
- Flag disagreements between sources when they exist.
- State the ranking criterion whenever a section ranks items.
- Cite reproductions and failures, not just original papers.
- Distinguish theoretical, empirical, and engineering contributions.
