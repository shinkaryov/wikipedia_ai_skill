# Iterative development and AI verification

## Development approach

AI assisted with interface design, implementation, tests and report layout. Verify generated work through independent arithmetic examples, real API responses, cache/network counters, report rendering, and an inexpensive model operating with minimal task-local context. Keep observed failures and fixes in validation evidence. Do not rely solely on AI review of its own generated code.

## Iteration 1: measured core article

Ship one concept, explicit languages and complete-month comparisons. Keep the CLI small; JSON outputs summarize computed facts. Validate the three task examples, missing-article outcomes and an unseen topic. Read raw source JSON for representative metrics. Do not broaden the scope before this loop works.

## Iteration 2: comparable topic baskets

Introduce a versioned manifest of related concepts with inclusion/exclusion reasons. Match basket coverage between languages, report coverage separately, avoid duplicate titles and avoid counting a redirect and its target twice. Never interpret summed pageviews as unique audience. Compare conclusions with a core-article-only baseline and perform leave-one-article-out sensitivity checks. Keep user-supplied and model-proposed articles distinguishable.

## Iteration 3: stronger time-series evidence

Add daily data only when a specific spike requires investigation; retain monthly aggregates for overview. Add documented title history and page move reconstruction before treating a discontinuity as interest change. Use 3-5 years when estimating seasonality. Evaluate any forecasting against historical holdouts and a simple seasonal baseline, reporting errors and prediction intervals; do not infer a forecast from a line fit alone.

## Iteration 4: larger data volumes

Estimate the request budget before fetching. Deduplicate concept/project requests, batch Wikidata entity lookups, persist task checkpoints, and fetch only missing monthly partitions. Add bounded concurrency only within Wikimedia's current policy; keep global rate control and Retry-After handling. Move indexed cache metadata to SQLite and observations to Parquet/DuckDB when file count and query volume justify it. Use official bulk dumps for genuinely broad repeated research rather than thousands of avoidable API calls.

## Iteration 5: product relevance

Add independently sourced search demand, customer interviews and first-party acquisition/conversion data. Keep evidence types separate. Define prospectiveness criteria with the user: growth vs audience scale, product fit, localization effort and monetization. Backtest whether Wikipedia signals usefully predict measured outcomes; remove metrics that do not improve decisions.

## Evaluation after each change

Keep deterministic fixtures unchanged unless a documented methodology change requires updating them. Expand held-out topics/languages. Compare model task completion, unsupported claims, number of tool calls, token cost, runtime, cache hit rate and PDF failures. Make one meaningful change at a time and retain before/after traces. Never tune only to the three assignment examples.
