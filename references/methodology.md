# Methodology v1.0

## Scope and source identity

Resolve a Wikidata item and obtain its sitelinks. Verify canonical page title, namespace, disambiguation status, Wikidata ID and earliest retained revision via the MediaWiki Action API. A missing sitelink, disambiguation page or ID mismatch is not an observed zero. Manual page overrides always require a scope note and are excluded from automatic shortlists.

Use `all-access`, `agent=user`, `granularity=monthly` consistently for articles and project totals. This excludes traffic Wikimedia classifies as bots, but does not guarantee perfect human identification. Counts describe views, not unique people.

Measure **current titles only**. Do not add redirect counts or claim full historical continuity. The earliest retained revision is a creation-date indicator, not proof that no move/merge occurred. Page moves, deleted revisions and article-scope differences can affect interpretation even when all months are returned. Language does not identify reader location.

## Periods and missing data

Use complete calendar months in UTC. Reject the current month, future dates, dates before 2015-07, reversed ranges and more than 120 months. Exclude no returned zeros. A missing API row, 404 or request failure becomes null, never zero. Preserve API failures separately from absent articles. Do not forward-fill, interpolate or automatically drop months. Averages/shares never pair observations with missing or nonpositive project totals.

## Metrics

Let A_m be article views and P_m be project views in month m.

- Monthly normalized interest = 1,000,000 * A_m / P_m, when both exist and P_m > 0.
- Last-12-month views = sum of A_m over the final 12 months, available only when all 12 are observed.
- Raw YoY = 100 * (sum(final 12 A_m) / sum(preceding 12 A_m) - 1).
- Annual share = sum(A_m) / sum(P_m); relative YoY compares annual shares, **not** unweighted averages of monthly ratios.
- Monthly YoY pairs each final-year month with the same calendar month in the previous year. Report median valid pair growth and number positive; prior zero pairs have undefined percentage growth.
- Zero annual baseline: percentage growth is undefined. Show null and explain, never infinity or 100%.
- Series longer than 24 months are plotted in full; summary growth uses the final 24 months and is labelled accordingly.

## Sensitivity and diagnostic flags

For every matched month pair i, calculate 100 * ((current annual total - current_i) / (previous annual total - previous_i) - 1), when the denominator is positive. Report the minimum/maximum. Separately report exclusion of the pair containing the largest final-year month. This preserves calendar matching. It is a sensitivity scenario, not a corrected history or removal of "bad" observations.

Possible spike threshold over the final 24 observations: median + max(6 * 1.4826 * MAD, 2 * max(median, 1)). A flagged peak may be seasonal or real; never infer its cause without external evidence and never remove it by default. Report if the largest final-year month exceeds 25% of final-year views.

`consistent`: all requested article/project months observed, sufficient history, positive baseline, no diagnostic flags. `caution`: calculable but has gaps elsewhere in a longer period, small baseline (<1,200 prior-year views), possible spikes, peak concentration, manual mapping, differing raw/relative directions or sensitivity to one pair. `insufficient`: <24 months, missing observations in the comparison window, zero prior-year total, creation within the requested period or inconsistent article/project counts. These thresholds are transparent MVP heuristics, **not** confidence levels or statistical significance tests. Consistent decline is possible.

## Recommendation rule

Automatic shortlist eligibility requires `consistent` stability and strictly positive raw and normalized YoY. Sort eligible languages by the declared criterion. Keep excluded languages visible with reasons. No opaque score, no inferred purchasing power, no revenue forecasts. The next step is targeted interviews and a measurable product/landing-page experiment. This conservative default can be revised later with an explicit rule change and validation.

## Caching and audit

Cache response envelopes keyed by request URL and verified with SHA-256. Cache per-series months that reference their source responses, deriving observations from checked source content on reuse. Fetch only missing/stale contiguous month ranges, at most 12 months per request. Cache recent months for one day, older months for 30 days, metadata for one day. `--refresh` bypasses caches. `--offline` may use stale snapshots but labels that choice. No stale fallback is silently used online.

Requests are sequential with bounded retries for 429/5xx and network errors. Respect Retry-After; if it exceeds 60 seconds, return an actionable error rather than retrying early. No retries for other HTTP errors. Runs save configuration, parent run, code/method version, request counts, URLs, timestamps, source hashes and copied response bodies. A code version is not a cryptographic commit hash; retain the distributed source/lockfile for exact reproduction.

## Primary documentation

- Agent Skills: https://agentskills.io/specification
- Pageviews API: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html
- View definitions and redirects: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/concepts/page-views.html
- User-Agent, rates, CC0: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html
- Wikibase API: https://www.mediawiki.org/wiki/Wikibase/API

Documentation checked during development on 2026-09-23. Sources can change; source snapshots accompany generated studies.