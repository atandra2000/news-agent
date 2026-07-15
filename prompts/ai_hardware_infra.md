# AI HARDWARE & INFRASTRUCTURE BRIEF

**Cadence:** weekly, focused on the compute layer.

Autonomous brief on the compute layer behind AI: chips, systems, cloud,
and serving infrastructure. Best run weekly.

# Research Instructions

For every factual claim, cite the exact source URL with the token
`[src:URL]` immediately after the claim. Prefer vendor specs, technical
blogs, and primary benchmark posts over press summaries.

## Official Sources

_Why these sources:_ chip vendors, hyperscalers, and inference providers
that publish first-party specs and benchmark posts.

- NVIDIA
- AMD
- Intel
- Google TPU
- AWS Trainium
- AWS Inferentia
- Microsoft Azure
- Groq
- Cerebras
- SambaNova
- Meta Infrastructure

## Research Sources

_Why these sources:_ open-access archives and leaderboards where new
architectural results and benchmark numbers surface first.

- arXiv
- Papers With Code
- Hugging Face
- Semantic Scholar

## Trusted News Sources

_Why these sources:_ newsrooms with track records on semiconductor and
infrastructure reporting.

- Reuters
- Bloomberg
- The Information
- IEEE Spectrum
- TechCrunch
- VentureBeat

## Community Intelligence

_Why these sources:_ developer communities that surface real-world
adoption, benchmark skepticism, and deployment war stories. Use for
sentiment, never as fact.

- Hacker News
- r/LocalLLaMA
- GitHub Trending
- Hugging Face Trending

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A list of
chip announcements is not a hardware brief.

1. **Compare chips on a consistent axis** (process node, memory type
   and capacity, peak FLOPS, interconnect bandwidth, power, price).
   Render a Markdown comparison table for the top in-scope chips.
2. **Compare rack-scale systems on a consistent axis** (GPU count,
   interconnect, memory pool, cooling, total power, software stack).
   Render a Markdown comparison table.
3. **Quantify** every claim: peak FP8/BF16/INT8 TFLOPS, HBM capacity
   and bandwidth, NVLink/PCIe generations, dollars per million tokens
   served, power per rack.
4. **Contrast** this period's silicon with the prior generation —
   what changed, what didn't, what's deferred.
5. **Surface** supply, pricing, and availability signals (lead times,
   allocation status, region-specific constraints). Distinguish
   vendor-claimed availability from real-world availability.
6. **Distinguish** vendor benchmarks from third-party benchmarks from
   community reproductions.

# Report Structure

_(use 8-12 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining hardware shifts this period
- supply, pricing, and availability signals
- one-sentence verdict

## 2. Training & Inference Silicon
- NVIDIA, AMD, Intel, TPU announcements
- process node, memory, bandwidth, compute
- _→ render as Markdown comparison table (Chip, Vendor, Process node,
  Memory, Peak BF16 TFLOPS, Notable use, Release)_

## 3. Systems & Racks
- rack-scale designs, networking, liquid cooling
- co-designed prefill/decode architectures
- what changed versus prior generation
- _→ render as Markdown comparison table when in-window rack
  announcements (System, GPU count, Interconnect, Memory pool,
  Cooling, Total power, Software)_

## 4. Inference & Serving Stack
- vLLM, TensorRT, serving frameworks
- kernel fusion, quantization, throughput gains
- community deployment experience
- _→ render as Markdown comparison table when in-window serving
  releases (Framework, Version, Throughput gain, Latency, Notable)_

## 5. Cloud & Capacity
- AWS, Azure, GCP, Oracle capacity
- sovereign and regional compute
- power, real-estate, and supply-chain constraints

## 6. Cost & Accessibility
- API pricing moves
- on-prem versus cloud tradeoffs
- what this means for small teams
- _→ render as Markdown comparison table for API pricing moves
  (Provider, Model, Input $/M tokens, Output $/M tokens, Change)_

## 7. Predictions
- next hardware generations
- capacity and pricing trajectory
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- **Markdown comparison table for silicon (Chip, Vendor, Process node, Memory, Peak BF16 TFLOPS, Notable use, Release)**
- **Markdown comparison table for systems/racks when in-window announcements exist**
- **Markdown comparison table for serving stack when in-window releases exist**
- **Markdown comparison table for API pricing moves (Provider, Model, Input $/M tokens, Output $/M tokens, Change)**
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified facts from analysis and community sentiment.
- Prefer primary sources; state when only social evidence exists.
- Quantify: FLOPS, HBM, bandwidth, pricing, availability dates.
- Use comparison tables for chips, systems, serving stacks, and pricing.
- Include publication dates for time-sensitive claims.
- Synthesize and explain significance; do not merely list specs.
- Flag disagreements between sources when they exist.
- State the ranking criterion whenever a section ranks items.
- Distinguish vendor-claimed availability from real-world availability.
