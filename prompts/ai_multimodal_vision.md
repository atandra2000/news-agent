# AI MULTIMODAL & GENERATIVE MEDIA BRIEF

**Cadence:** weekly, focused on multimodal AI across modalities.

Autonomous brief on multimodal AI: vision-language models, image
generation, video generation, audio/speech, and unified multimodal
architectures. Best run weekly.

# Research Instructions

For every factual claim, cite the exact source URL with the token
`[src:URL]` immediately after the claim. Prefer model cards, demo
reels, technical reports, and benchmark leaderboards over press
summaries.

## Official Sources

_Why these sources:_ the labs and vendors that publish first-party
model cards, demo pages, and benchmark results.

- OpenAI (Sora, GPT-4o, DALL-E, Whisper)
- Anthropic (Claude vision)
- Google DeepMind (Gemini, Veo, Imagen)
- Google AI (Gemini, Veo, Imagen)
- Meta AI (Llama multimodal, Movie Gen, SAM)
- xAI (Grok vision)
- Midjourney
- Stability AI (Stable Diffusion, Stable Video)
- Black Forest Labs (FLUX)
- Runway (Gen)
- Pika
- ElevenLabs
- Suno
- Udio
- Mistral (Pixtral)
- Alibaba Qwen (Qwen-VL, Wan)
- Kuaishou (Kling)

## Research Sources

_Why these sources:_ open-access archives and venue proceedings where
multimodal research is canonical.

- arXiv (cs.CV, cs.MM, cs.SD, eess.AS)
- Papers With Code
- Hugging Face
- Semantic Scholar
- NeurIPS / CVPR / ICCV / ECCV

## Trusted News Sources

_Why these sources:_ newsrooms with track records on multimodal AI
reporting.

- MIT Technology Review
- The Information
- TechCrunch
- IEEE Spectrum
- VentureBeat
- Reuters
- Bloomberg

## Community Intelligence

_Why these sources:_ creative and developer communities that surface
real-world adoption, prompt techniques, and benchmark skepticism. Use
for sentiment, never as fact.

- Hacker News
- r/StableDiffusion
- r/MachineLearning
- r/aivideo
- Civitai
- Hugging Face Spaces
- GitHub Trending
- X (multimodal researchers)

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A list
of model releases is not a multimodal brief.

1. **Compare within each modality on a consistent axis** — for VLM
   (Model, Developer, Context, MMMU, MathVista, ChartQA, DocVQA,
   Release); for image (Model, Resolution, Adherence, Editability,
   License); for video (Model, Max length, Coherence, Controllability,
   License); for audio (Model, Sample rate, Latency, Voice cloning,
   License). Render a Markdown comparison table per modality.
2. **Rank by capability on the user's task, not by release date.**
   State the ranking criterion.
3. **Quantify** every claim: parameter counts, resolution, duration,
   sample rate, benchmark scores, dates, license terms.
4. **Contrast** this period's multimodal moves with the prior period —
   what shifted, what was incremental, what was retracted.
5. **Surface capability gaps explicitly** — text-only vs multimodal,
   short-context vs long-context, single-modality vs unified.
6. **Distinguish** vendor demos, third-party evaluations, and
   community reproductions. State the eval set.

# Report Structure

_(use 8-12 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining multimodal shifts this period
- who released, who gained capability
- one-sentence verdict

## 2. Vision-Language Models
- new VLM releases, architecture, context
- benchmark standing (MMMU, MathVista, ChartQA, DocVQA)
- _→ render as Markdown comparison table (Model, Developer, Context,
  MMMU, MathVista, ChartQA, DocVQA, Release)_

## 3. Image Generation
- new models and updates
- prompt adherence, photorealism, typography, editability
- _→ render as Markdown comparison table (Model, Developer,
  Resolution, Adherence, Editability, License, Release)_

## 4. Video Generation
- new models, length, coherence, controllability
- comparison across Sora, Veo, Kling, Runway, Pika
- _→ render as Markdown comparison table (Model, Developer, Max
  length, Coherence, Controllability, License, Release)_

## 5. Audio & Speech
- TTS, voice cloning, music generation
- real-time vs offline, latency, quality
- notable releases and benchmarks
- _→ render as Markdown comparison table (Model, Developer, Sample
  rate, Latency, Voice cloning, License, Release)_

## 6. Unified Multimodal Architectures
- any-to-any models, joint embedding spaces
- early-fusion vs late-fusion
- emergent capabilities

## 7. Creative & Production Adoption
- studio, advertising, gaming, social media
- real workflows and tools
- legal and copyright landscape

## 8. Predictions & Watchlist
- next multimodal milestones
- capability trajectories
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- **Markdown comparison table for VLMs (Model, Developer, Context, MMMU, MathVista, ChartQA, DocVQA, Release)**
- **Markdown comparison table for image generation (Model, Developer, Resolution, Adherence, Editability, License, Release)**
- **Markdown comparison table for video generation (Model, Developer, Max length, Coherence, Controllability, License, Release)**
- **Markdown comparison table for audio/speech (Model, Developer, Sample rate, Latency, Voice cloning, License, Release)**
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified facts from demos and community sentiment.
- Prefer primary sources (model cards, demo pages, technical reports).
- Quantify: parameter counts, resolution, duration, benchmark scores.
- Use comparison tables for models across modalities — one table per modality.
- Include release dates and license terms.
- Synthesize capability shifts, not just release lists.
- Flag when claims are based on demos vs third-party evaluations.
- State the ranking criterion whenever a section ranks items.
- Distinguish vendor demos, third-party evaluations, and community reproductions.
