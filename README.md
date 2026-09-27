# Wikipedia Interest Research

An Agent Skill for B2C founders exploring which topics and language audiences deserve further product validation. It resolves equivalent Wikipedia articles through Wikidata, retrieves pageviews, computes growth and stability diagnostics, and produces a one-page report with source evidence.

Wikipedia views measure attention, not purchase intent. Language editions do not identify countries. The MVP measures one core article per language, not the entire topic.

## Files and requirements

- `SKILL.md`: instructions for an agent with terminal access.
- `references/methodology.md`: formulas, quality rules, limitations and sources.
- `scripts/`: retrieval, analysis, rendering and optional model evaluation.
- `tests/`: deterministic and artifact checks.
- `examples/`: two complete studies and historical evaluation evidence.
- `Dockerfile`, `pyproject.toml`, `uv.lock`: reproducible environment.

Use Docker with a working daemon, or Python 3.11+ and uv. Live research needs network access to Wikimedia/Wikidata. Building needs access to image registries and PyPI. The model runs outside the container and invokes the CLI through a terminal tool; loading SKILL.md alone does not execute it.

## Environment

Run commands from this directory. On first setup:

```bash
cp .env.example .env
```

Edit `.env`: replace the contact in `WIKIMEDIA_USER_AGENT`. Keep values unquoted for Docker compatibility. `OPENROUTER_API_KEY` is optional and needed only for the OpenRouter evaluation runner. Wikimedia does not require an API key. Keep `.env` private; it is ignored by Git and excluded from the image. The Python CLI does not automatically load dotenv files.

## Docker

The following commands use a POSIX shell (macOS/Linux). Check daemon availability with `docker info`.

```bash
docker build -t wiki-interest-research:local .
mkdir -p .cache runs

wiki() {
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$(pwd)/.cache,target=/app/.cache" \
    --mount "type=bind,source=$(pwd)/runs,target=/app/runs" \
    --env-file .env \
    wiki-interest-research:local "$@"
}
```

The mounts preserve cache and outputs after container exit. Keep container paths unchanged for follow-ups because manifests contain absolute cache paths. Translate `/app/runs/...` in CLI output to the host's `./runs/...` when opening files. Redefine the wrapper if the terminal does not retain shell state.

## Native alternative

If Docker is unavailable, install locked dependencies and define the same command:

```bash
uv sync --frozen
wiki() {
  uv run --env-file .env --frozen python scripts/wiki_interest.py "$@"
}
```

Do not install a Docker daemon during an agent research request. Use one execution mode consistently; replay is the portable way to transfer a study between environments.

## Research and follow-ups

```bash
wiki discover --topic astronomy --languages uk cs --search-language en
# Select the matching QID returned by discovery; Q333 is astronomy.
wiki run --qid Q333 --languages uk cs --start 2024-01 --end 2025-12 --out runs/astronomy-01
wiki revise --run runs/astronomy-01 --languages uk cs pl --out runs/astronomy-02
wiki revise --run runs/astronomy-02 --criterion volume --offline --out runs/astronomy-03
```

Use a fresh output directory each time. Defaults: last 24 complete UTC months, one concept, 1-5 languages, criterion `balanced`. Explicit ranges start no earlier than July 2015 and span at most 120 months. Annual growth requires the final 24 complete observed months.

Criteria rank only languages passing the same stability and positive raw/normalized growth gates: `balanced` sorts by normalized growth then volume; `growth` by raw growth then volume; `volume` by annual views then normalized growth. This is a shortlist for further research, not a launch recommendation.

Missing articles remain unmeasured. Manual `--page 'pl:Exact title'` requires `--scope-note` and is excluded from automatic shortlists. Search candidates with `wiki search-pages --topic 'local topic phrase' --language pl`. Read [the methodology](references/methodology.md) before interpreting results.

## Outputs

Each completed study includes:

| File | Purpose |
| --- | --- |
| `brief.pdf`, `brief.md` | One-page PDF and Markdown summary |
| `trend.png`, `trend.svg` | Absolute and normalized trends |
| `monthly.csv`, `metrics.json` | Observations and computed metrics |
| `manifest.json` | Parameters, status and run provenance |
| `sources.json`, `sources/` | Source index and exact response evidence |

The report is English; the agent explains findings in the user's language. Read JSON stdout for status, warnings, errors and artifact paths. Partial or failed reports must not be presented as complete. After a rendering failure, preserve data, fix the environment and run `wiki render --run runs/astronomy-01`.

## Offline replay and reproducibility

Replay validates source checksums and recomputes from saved responses; render only rebuilds presentation from metrics. After building the image, this check needs neither network nor an existing cache:

```bash
mkdir -p runs
docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$(pwd)/runs,target=/app/runs" \
  wiki-interest-research:local \
  replay --run examples/astronomy-uk-cs --out runs/docker-replay-01
```

Native equivalent after installing dependencies:

```bash
uv run --frozen python scripts/wiki_interest.py replay --run examples/astronomy-uk-cs --out runs/native-replay-01
```

For shared studies, copy the complete bundle under `runs/` and use its path as `--run`. Python 3.12.14 and uv 0.12.18 Docker images are pinned by digest; dependencies use `uv.lock`. Record the source revision, image ID, platform, manifest and evidence. Add `--platform linux/amd64` to both Docker build and run when matching that architecture; ARM may require emulation. Use explicit dates and saved responses: live data and relative windows can change. PDF bytes may differ due to metadata.

## Validation and AI-assisted development

AI assisted with interface design, implementation, tests and report layout. Verification used independent arithmetic, real responses, cache/network counters, rendered reports and an inexpensive model with fresh task context.

Run deterministic/artifact checks separately:

```bash
uv run --frozen python -m unittest discover -s tests -v
```

Checks cover growth, normalization, calendar matching, spike sensitivity, missing vs zero data, mapping, dates, caching, retries, source checksums and report recovery. For model evaluation, provide only the skill and an ordinary request, without expected QIDs or answers. Use astronomy, fasting, learning-English, add-language and offline-ranking scenarios, plus held-out topics.

The optional OpenRouter runner requires a tool-capable model and a key in `.env`:

```bash
uv run --env-file .env --frozen python scripts/evaluate_openrouter.py --model anthropic/claude-haiku-4.5 --scenario astronomy --out runs/openrouter-astronomy
```

Check current model availability, tool support and pricing before use. Inspect traces: success requires executed tools, correct scope, preserved gaps, a one-page PDF, grounded numbers, explained limitations and cache reuse. Clarification or insufficient evidence can be valid outcomes. Record model identity, commands, artifacts, duration, requests and provider-reported usage/cost. Planned scenarios are not completed tests.

`examples/validation.json` and `examples/test-results.txt` record the 2026-09-26 baseline: 26 checks passed and gpt-6-luna agent evaluations were recorded. These results predate packaging changes. Chess and English-learning artifacts are no longer bundled; their historical records remain. Docker build/runtime has not been tested in the authoring environment because Docker is unavailable; image digests were resolved successfully.

Keep only `examples/astronomy-uk-cs/` and `examples/fasting-pl-cs/` as complete sample studies. Retain `agent_scenarios.json` for the runner and the historical evidence files. Write new outputs under ignored `runs/`.

## Further development

1. Add versioned topic baskets with inclusion reasons, matched cross-language coverage and deduplication. Compare against the core-article baseline and leave-one-article-out sensitivity; summed views are not unique users.
2. Add title/move history and daily evidence for specific spikes. Use longer histories for seasonality. Evaluate forecasts against historical holdouts and seasonal baselines before reporting uncertainty intervals.
3. Scale with request budgets, shared cache deduplication, batched metadata and checkpoints. Add bounded concurrency respecting Wikimedia policy. Move cache indexes to SQLite and observations to Parquet/DuckDB when warranted; consider official bulk data for broad studies.
4. Add search demand, interviews and first-party conversion evidence. Define product fit, localization cost and monetization criteria explicitly; test whether pageview signals predict useful outcomes.
5. After each change, retain comparable fixtures and before/after traces. Measure unsupported claims, completion, requests, tokens, runtime and cache reuse across new topics/languages.

## Documentation

- [Agent Skills specification](https://agentskills.io/specification)
- [Wikimedia Pageviews API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html)
- [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/)
- [OpenRouter tool calling](https://openrouter.ai/docs/guides/features/tool-calling)