# AI HARDWARE & INFRASTRUCTURE BRIEF#

Autonomous brief on the compute layer behind AI: chips, systems, cloud,
and serving infrastructure. Best run weekly or monthly.

# Research Instructions#

For every factual claim, cite the exact source URL with the token
[src:URL] immediately after the claim. Prefer vendor specs, technical
blogs, and primary benchmark posts over press summaries.

## Official Sources
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
- arXiv
- Papers With Code
- Hugging Face
- Semantic Scholar

## Trusted News Sources
- Reuters
- Bloomberg
- The Information
- IEEE Spectrum
- TechCrunch
- VentureBeat

## Community Intelligence
- Hacker News
- r/LocalLLaMA
- GitHub Trending
- Hugging Face Trending

Use community sources for real-world adoption, benchmarks skepticism,
and deployment war stories. Never present opinion as fact.

# Report Structure#

## 1. Executive Summary
- defining hardware shifts this period
- supply, pricing, and availability signals
- one-sentence verdict

## 2. Training & Inference Silicon
- NVIDIA, AMD, Intel, TPU announcements
- process node, memory, bandwidth, compute
- render as a comparison table

## 3. Systems & Racks
- rack-scale designs, networking, liquid cooling
- co-designed prefill/decode architectures
- what changed versus prior generation

## 4. Inference & Serving Stack
- vLLM, TensorRT, serving frameworks
- kernel fusion, quantization, throughput gains
- community deployment experience

## 5. Cloud & Capacity
- AWS, Azure, GCP, Oracle capacity
- sovereign and regional compute
- power, real-estate, and supply-chain constraints

## 6. Cost & Accessibility
- API pricing moves
- on-prem versus cloud tradeoffs
- what this means for small teams

## 7. Predictions
- next hardware generations
- capacity and pricing trajectory
- clearly labeled as informed predictions

# Required Deliverables#
- Executive summary
- Silicon comparison table
- Systems and serving coverage
- Inline [src:URL] citations
- A References section

# Output Quality Requirements#
- Cite every factual claim with [src:EXACT_URL].
- Separate verified facts from analysis and community sentiment.
- Prefer primary sources; state when only social evidence exists.
- Quantify: FLOPS, HBM, bandwidth, pricing, availability dates.
- Use comparison tables for chips and systems.
- Include publication dates for time-sensitive claims.
- Synthesize and explain significance; do not merely list specs.
- Flag disagreements between sources when they exist.
