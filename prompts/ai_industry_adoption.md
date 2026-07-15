# AI INDUSTRY ADOPTION & VERTICAL APPS BRIEF

**Cadence:** monthly, focused on real-world deployment.

Autonomous brief on AI deployment in real industries: healthcare, finance,
legal, defense, software engineering, education, retail, and manufacturing.
Best run monthly.

# Research Instructions

For every factual claim, cite the exact source URL with the token
`[src:URL]` immediately after the claim. Prefer case studies, FDA filings,
SEC disclosures, peer-reviewed studies, and primary press over vendor
marketing.

## Official Sources

_Why these sources:_ regulators, customers, and government buyers that
publish first-party disclosures on deployed AI.

- FDA (AI/ML medical devices)
- NIH / NCI
- Epic Systems
- Mayo Clinic AI
- Kaiser Permanente
- HCA Healthcare
- JPMorgan
- Goldman Sachs
- Two Sigma
- Citadel
- Bloomberg
- Visa / Mastercard AI
- Thomson Reuters
- LexisNexis
- DoD CDAO
- DARPA
- Palantir
- Anduril
- Shopify
- Duolingo
- Khan Academy

## Research Sources

_Why these sources:_ peer-reviewed venues and archives where
domain-AI research is canonical.

- arXiv
- Papers With Code
- JAMA / NEJM AI
- Nature Medicine
- Semantic Scholar

## Trusted News Sources

_Why these sources:_ industry-specific newsrooms with track records on
AI deployment reporting.

- Reuters
- Bloomberg
- Wall Street Journal
- Financial Times
- The Information
- TechCrunch
- STAT News
- Modern Healthcare
- Banking Dive
- Law360

## Community Intelligence

_Why these sources:_ practitioner communities that surface production
war stories and adoption friction. Use for sentiment, never as fact;
never present vendor marketing as fact.

- Hacker News
- r/MachineLearning
- r/LocalLLaMA
- industry Slack and Discord groups
- LinkedIn (AI practitioners)

# Synthesis Directives

The writer MUST apply these synthesis verbs to every section. A list
of case studies is not an adoption brief.

1. **Distinguish deployed, piloted, and announced explicitly.**
   Each claim should declare which of the three it covers, not blend
   them.
2. **Rank by measurable impact, not by press release volume.** State
   the ranking criterion (productivity gain, cost reduction, accuracy,
   scale of deployment).
3. **Compare industries on a consistent axis** (deployment scale,
   measurable outcome, governance maturity, vendor concentration).
   Render a Markdown comparison table for in-scope verticals.
4. **Quantify** every claim: productivity gain (%), cost reduction
   (%), accuracy, latency, deployment scale (users, transactions,
   sites).
5. **Contrast** this period's adoption with the prior period — what
   scaled, what stalled, what rolled back.
6. **Surface adoption friction explicitly** — accuracy, latency,
   cost, integration, governance, vendor lock-in.
7. **Distinguish** vendor claims, peer-reviewed evidence, and
   anecdotal reports. State the evidence type for each claim.

# Report Structure

_(use 8-12 sources per section; prefer 2 official + 2 research + 1 news +
1 community)_

## 1. Executive Summary
- defining industry adoption shifts this period
- measurable productivity and revenue moves
- one-sentence verdict

## 2. Healthcare & Life Sciences
- clinical AI deployments and FDA clearances
- drug discovery, genomics, clinical workflow
- measurable outcomes where available
- _→ render as Markdown comparison table for top deployments
  (Use case, Vendor/Customer, Scale, Outcome, Date)_

## 3. Finance & Trading
- trading, risk, fraud, compliance, customer service
- measurable performance and cost reduction
- regulatory posture

## 4. Legal & Compliance
- document review, contract analysis, e-discovery
- law firm and in-house adoption
- bar association and court rules

## 5. Software Engineering
- AI-assisted coding adoption rates
- measured productivity, code quality, security impact
- developer experience
- _→ render as Markdown comparison table for measurable outcomes
  (Vendor, Productivity gain, Code quality, Security, Date)_

## 6. Defense & Government
- DoD, intelligence community, civilian agency deployments
- procurement patterns and ethics review
- international comparisons

## 7. Education, Retail & Manufacturing
- tutoring, content, customer service
- supply chain, design, predictive maintenance
- adoption signals vs measurable impact

## 8. Adoption Friction
- accuracy, latency, cost, integration, governance
- vendor consolidation and switching
- failure modes and rollbacks

## 9. Predictions & Watchlist
- next vertical breakthroughs
- adoption trajectory by industry
- clearly labeled as informed predictions

# Required Deliverables

- Executive summary
- **Markdown comparison table for industry deployments (Use case, Vendor/Customer, Scale, Outcome, Date)**
- **Markdown comparison table for measurable outcomes (Vendor, Productivity gain, Code quality, Security, Date)**
- Inline `[src:URL]` citations
- A References section

# Output Quality Requirements

- Cite every factual claim with `[src:URL]`.
- When a fact comes from industry knowledge rather than a cited source, tag it explicitly: `[unsourced — industry knowledge]`.
- Separate verified outcomes from vendor claims.
- Prefer peer-reviewed studies, regulatory filings, and primary press.
- Quantify: productivity gains, cost reduction, accuracy, latency.
- Use comparison tables for industry metrics and measurable outcomes.
- Include deployment dates and scale (users, transactions, sites).
- Distinguish deployed from piloted from announced.
- Flag when evidence is anecdotal vs measured.
- State the ranking criterion whenever a section ranks items.
- State the evidence type (peer-reviewed, vendor, anecdotal) for each claim.
