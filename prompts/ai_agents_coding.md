# AI AGENTS & CODING TOOLS BRIEF

**Cadence:** weekly, focused on coding agents and agent platforms.

Autonomous brief on coding agents, agent platforms, and the
agentic-software toolchain. Best run weekly.

# Research Instructions

For every factual claim, cite the exact source URL with the token
`[src:URL]` immediately after the claim. Prefer official changelogs,
technical blogs, and benchmark repos over press coverage.

## Official Sources

_Why these sources:_ the labs and vendors that publish first-party
changelogs, model cards, and platform releases.

- OpenAI (Codex / GPT)
- Anthropic (Claude Code)
- Google (Gemini CLI)
- OpenCode
- GitHub Copilot
- Cursor
- Replit
- Windsurf
- OpenHands
- Cognition (Devin)
- Lovable
- Bolt
- Vercel (v0)
- Model Context Protocol

## Research Sources

_Why these sources:_ open-access archives and leaderboards where new
agent methods and benchmark results surface first.

- arXiv
- Papers With Code
- Hugging Face
- Semantic Scholar

## Trusted News Sources

_Why these sources:_ newsrooms with track records of accurate tech
reporting and access to off-record industry sources.

- The Information
- MIT Technology Review
- TechCrunch
- VentureBeat
- IEEE Spectrum

## Community Intelligence

_Why these sources:_ developer communities that surface real-world
adoption, benchmark skepticism, and production war stories. Use for
sentiment, never as fact.

- Hacker News
- r/LocalLLaMA
- r/MachineLearning
- r/singularity
- GitHub Trending
- Hugging Face Trending

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A list
of agent tools is not an agents brief.

1. **Rank by production adoption, not feature list.** State the
   ranking criterion explicitly (e.g. SWE-bench Verified, retention,
   enterprise wins, developer NPS).
2. **Compare agents on a consistent axis** (terminal vs IDE vs
   browser, autonomous vs assisted, model flexibility, MCP support,
   reliability). Render a Markdown comparison table for the top
   tools in scope.
3. **Quantify** every claim: benchmark scores, pricing per seat or
   per token, context window, success rate, time-to-PR.
4. **Contrast** this period's moves with the prior period — what
   shipped, what regressed, what got acquired.
5. **Surface the "80% problem"** — agents that handle 80% of routine
   tasks but fail on the long tail. State the failure mode explicitly.
6. **Distinguish** vendor benchmarks, third-party benchmarks, and
   community reproductions. State the eval set used.

# Report Structure

_(use 8-12 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining agentic shifts this period
- who gained or lost ground
- one-sentence verdict

## 2. Coding Agents
- Claude Code, Codex CLI, Gemini CLI, OpenCode
- terminal vs IDE vs browser workflows
- reliability and real-world adoption
- _→ render as Markdown comparison table (Agent, Vendor, Surface,
  Model flexibility, MCP, Reliability, Notable change)_

## 3. Agent Platforms & Orchestration
- multi-agent systems and orchestration
- MCP / A2A ecosystem maturity
- memory, evaluation, and security

## 4. Benchmark & Capability
- SWE-bench, terminal-bench, agent evals
- scores, limitations, and overfitting notes
- _→ render as Markdown comparison table (Agent, Benchmark, Score,
  Eval set, Date)_

## 5. Developer Adoption & Sentiment
- favorite tools and workflows
- criticisms and the "80% problem"
- production lessons from the community

## 6. Pricing & Enterprise
- per-agent pricing moves
- enterprise deals and distribution plays
- what this means for teams
- _→ render as Markdown comparison table when in-window pricing
  changes (Tool, Plan, $/seat or $/M tokens, Change)_

## 7. Predictions
- next agent capabilities
- platform consolidation trajectory
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- **Markdown comparison table for coding agents (Agent, Vendor, Surface, Model flexibility, MCP, Reliability, Notable change)**
- **Markdown comparison table for benchmark scores (Agent, Benchmark, Score, Eval set, Date)**
- **Markdown comparison table for pricing moves when in-window changes exist**
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified facts from analysis and community sentiment.
- Prefer primary sources; state when only social evidence exists.
- Quantify: benchmark scores, pricing, adoption, dates.
- Use comparison tables for agents, benchmarks, and pricing.
- Include publication dates for time-sensitive claims.
- Synthesize and explain significance; do not merely list tools.
- Flag disagreements between sources when they exist.
- State the ranking criterion whenever a section ranks items.
- Distinguish vendor benchmarks from third-party evaluations.
