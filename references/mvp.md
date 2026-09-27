# MVP specification

## Product question

Help B2C founders decide which topic/language audiences deserve **further validation**, using Wikipedia article traffic as an imperfect interest proxy.

## Inputs and defaults

- One concept per study; 1-5 user-selected Wikipedia language codes.
- Last 24 complete UTC months by default; explicit month range supported from July 2015, at most 120 months.
- One current canonical article per language, matched through a common Wikidata item.
- Explicit manual page overrides with a scope note, flagged as less comparable.
- Criteria: balanced (normalized growth then volume), growth (raw growth then volume), volume (annual views then normalized growth). Apply the same quality and positive-growth gates before ranking.
- English PDF, Unicode Latin/Cyrillic article names, user-language conversational explanation.

## Outputs

One-page PDF; absolute and normalized time-series PNG/SVG; Markdown brief; monthly CSV; metrics JSON; immutable run manifest; exact source responses, fetch timestamps and checksums. Every numeric statement in the generated report comes from computed metrics.

## Acceptance scenarios

1. Intermittent fasting, Polish/Czech, 24 months: resolve the concept, preserve any missing language, do not substitute another diet silently, produce a transparent report.
2. Astronomy, Ukrainian, 24 months: report raw/relative growth and sensitivity; recommend a product validation step.
3. Learning English, selected languages: inspect intended learning scope; a general language article requires an explicit proxy assumption. Missing equivalent articles are a valid evidence limitation.
4. Add a language: retain prior dates and mapping, request only missing data.
5. Change ranking criterion offline: produce a new auditable report with zero network requests.
6. API failure or absent observation: preserve missing values, show the failure and withhold unsupported metrics.

## Deliberate boundaries

No country demand, unique-user estimation, willingness-to-pay prediction, causal explanations from pageviews alone, automated content-topic expansion or statistical forecasting in v0.1. The tool offers descriptive sensitivity checks, not calibrated confidence probabilities. Broad interests such as astronomy are measured using a core article and do not claim to cover every subtopic.
