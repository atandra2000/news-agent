# AI COMPANIES & STARTUPS BRIEF

**Cadence:** weekly, focused on the company landscape.

Autonomous brief on the AI company landscape: lab moves, startup
formations, founder and talent flow, executive changes, and
strategic positioning. Best run weekly.

# Research Instructions

For every factual claim, cite the exact source URL with the token
`[src:URL]` immediately after the claim. Prefer SEC filings, official
company announcements, and reputable financial press over rumor.

## Official Sources

_Why these sources:_ the labs, hyperscalers, and startups that publish
first-party announcements, filings, and blog posts.

- OpenAI
- Anthropic
- Google DeepMind
- Meta AI
- xAI
- Microsoft AI
- NVIDIA
- Mistral AI
- DeepSeek
- Cohere
- Perplexity
- Databricks
- Snowflake
- Scale AI
- Hugging Face
- GitHub
- Replit
- Cursor
- Cognition
- Glean
- Sierra

## Research Sources

_Why these sources:_ open-access archives and leaderboards where
company-relevant research is canonical.

- arXiv
- Semantic Scholar
- Hugging Face
- Papers With Code

## Trusted News Sources

_Why these sources:_ business and financial newsrooms with track
records on company-coverage reporting.

- Reuters
- Bloomberg
- Financial Times
- Wall Street Journal
- The Information
- TechCrunch
- Fortune
- Semafor
- Axios
- CNBC
- Business Insider

## Community Intelligence

_Why these sources:_ practitioner communities that surface talent
flow signals and rumor verification. Use for sentiment, never as
fact; label speculation explicitly.

- Hacker News
- r/MachineLearning
- r/singularity
- LinkedIn (AI executives)
- X (AI lab accounts and founders)
- Tech Twitter / Bluesky

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A list
of company news is not a companies brief.

1. **Distinguish confirmed, rumored, and reported explicitly.**
   Each claim should declare which of the three it covers, not
   blend them.
2. **Rank startups by traction, not by funding size alone.** State
   the ranking criterion (revenue, growth, enterprise wins,
   developer adoption, retention).
3. **Compare startups on a consistent axis** (sector, traction
   signal, funding to date, headcount, recent round). Render a
   Markdown comparison table for in-scope startups.
4. **Quantify** every claim: round sizes, valuations, headcount,
   revenue, growth, dates.
5. **Contrast** this period's company moves with the prior period —
   who accelerated, who stalled, who pivoted.
6. **Surface talent flow explicitly** — notable executive moves,
   researcher transitions, founding teams, notable hires.
7. **Distinguish** strategic partnerships from acqui-hires from
   outright acquisitions.

# Report Structure

_(use 8-12 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining company and talent moves this period
- winners, losers, and the most interesting shifts
- one-sentence verdict

## 2. Major Lab Strategy
- OpenAI, Anthropic, Google DeepMind, Meta AI, xAI, Microsoft
- product launches, partnerships, restructuring
- compute and infrastructure commitments

## 3. Notable Startups
- new AI companies and their positioning
- notable Series A/B/C and growth-stage raises
- _→ render as Markdown comparison table (Company, Sector, Traction
  signal, Funding to date, Headcount, Last round)_

## 4. Founder & Talent Flow
- notable executive moves and departures
- researcher transitions between labs
- founding teams and notable hires

## 5. Partnerships & Distribution
- cloud, compute, and distribution deals
- OEM, device, and channel partnerships
- enterprise vs developer go-to-market

## 6. Acquisitions & Talent Acqui-hires
- confirmed deals, rumored deals, and acqui-hires
- strategic rationale and integration status

## 7. Public Markets
- AI-adjacent public companies and their moves
- earnings calls, guidance, and analyst reaction
- IPO pipeline and post-IPO performance
- _→ render as Markdown comparison table for AI-adjacent public
  companies (Ticker, Market cap, Revenue growth, Notable move)_

## 8. Predictions & Watchlist
- next expected moves
- companies to watch
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- **Markdown comparison table for notable startups (Company, Sector, Traction signal, Funding to date, Headcount, Last round)**
- **Markdown comparison table for AI-adjacent public companies (Ticker, Market cap, Revenue growth, Notable move)**
- Talent flow log
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified moves from rumor; label speculation explicitly.
- Prefer primary sources (SEC filings, official announcements).
- Quantify: round sizes, valuations, headcount, dates.
- Use comparison tables for raises, headcount, and market cap.
- Include announcement dates and effective dates.
- Distinguish confirmed from rumored from reported claims.
- Flag when sources disagree on facts (e.g. deal size).
- State the ranking criterion whenever a section ranks items.
- Distinguish strategic partnerships from acqui-hires from outright acquisitions.
