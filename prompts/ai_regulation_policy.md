# AI REGULATION & POLICY TRACKER

**Cadence:** weekly, focused on governance and enforcement.

Autonomous brief on AI governance, law, and policy across jurisdictions.
Best run weekly to track an evolving, fragmented landscape.

# Research Instructions

For every factual claim, cite the exact source URL with the token
`[src:URL]` immediately after the claim. Prefer primary sources:
official registers, statutes, agency press, and court filings.

## Official Sources

_Why these sources:_ the regulators, agencies, and supranational bodies
that publish the binding rules and enforcement actions.

- European Commission (EU AI Act)
- US NIST AI
- US White House OSTP
- UK AI Safety Institute
- China CAC
- India MeitY
- Singapore IMDA
- Japan METI
- UN AI Advisory
- FTC
- EEAS

## Research Sources

_Why these sources:_ open-access archives where policy-relevant
research is canonical.

- arXiv
- Semantic Scholar
- Papers With Code
- Hugging Face

## Trusted News Sources

_Why these sources:_ newsrooms with track records on policy and
enforcement reporting.

- Reuters
- Bloomberg
- Financial Times
- The Information
- MIT Technology Review
- TechCrunch
- VentureBeat
- Semafor

## Community Intelligence

_Why these sources:_ practitioner communities that surface compliance
war stories and regulatory sentiment. Use for sentiment, never as fact.

- Hacker News
- r/singularity
- r/MachineLearning
- GitHub Trending

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A list
of regulatory actions is not a policy brief.

1. **Distinguish rule-making, enforcement, and litigation cleanly.**
   Each section should declare which it covers, not blend them.
2. **Compare jurisdictions on a consistent axis** (rule status,
   effective date, scope, penalties, enforcement record). Render
   a Markdown comparison table for in-scope jurisdictions.
3. **Quantify** every claim: fine amounts, compliance deadlines,
   compute thresholds, effective dates, reporting obligations.
4. **Contrast** this period's regulatory moves with the prior
   period — what's accelerating, what's slowing, what new
   jurisdictions are entering.
5. **Surface conflicts** between jurisdictions (e.g. EU vs US on
   foundation-model obligations, China vs EU on generative
   content). State the conflict, do not pick a side silently.
6. **Distinguish** binding rules from guidance from drafts from
   statements of intent.

# Report Structure

_(use 6-10 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining policy shifts this period
- highest-impact enforcement actions
- one-sentence verdict

## 2. United States
- federal and state actions
- agency guidance and enforcement
- litigation and executive orders

## 3. European Union
- AI Act phase-in and enforcement
- EU AI Office and standards
- member-state implementation

## 4. United Kingdom & Europe
- UK AISI and regime
- Switzerland, Norway, and others

## 5. China & Asia
- CAC rules and algorithm filing
- India MeitY and IT Rules
- Japan, Singapore, South Korea

## 6. Safety, Copyright & Open Source
- frontier-model obligations
- copyright and training-data law
- open-weight and dual-use policy

## 7. Enforcement & Litigation
- major suits and rulings
- penalties and remedies
- compliance implications for builders
- _→ render as Markdown comparison table for enforcement actions
  (Jurisdiction, Action, Target, Penalty, Date)_

## 8. International Cooperation
- treaties, frameworks, and coalitions
- standards bodies and interoperability

## 9. Predictions
- next regulatory moves
- compliance cost trajectory
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- Per-jurisdiction coverage
- **Markdown comparison table for enforcement actions (Jurisdiction, Action, Target, Penalty, Date)**
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified facts from analysis and community sentiment.
- Prefer primary sources; state when only press/social evidence exists.
- Quantify: fines, deadlines, thresholds, effective dates.
- Use a comparison/enforcement table across jurisdictions.
- Include effective dates for time-sensitive rules.
- Synthesize and explain significance; do not merely list actions.
- Flag disagreements between sources when they exist.
- State the ranking criterion whenever a section ranks items.
- Distinguish binding rules from guidance from drafts from statements of intent.
- Surface jurisdictional conflicts explicitly.
