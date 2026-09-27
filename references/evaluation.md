# Evaluation

## Reproducible checks

From the skill directory:

```bash
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -v
```

Unit/integration checks cover growth vs project growth, calendar matching, single-spike reversal, absent vs zero observations, zero baseline, short histories, manual/non-equivalent mapping, missing denominators, new articles, disambiguation, date boundaries, overlapping cache windows, offline reuse, URL encoding, retry policy and source checksum failures.

## Agent scenarios

Use a fresh tool-capable inexpensive model with only this SKILL.md, relevant references and a normal user request. Do not provide expected article IDs, metrics or answers. Execute the tools, not just a proposed command. Inspect the final report and tool trace independently.

- "Is interest in astronomy growing in Ukrainian Wikipedia over the last two years? How much can we trust the increase? Create a short PDF."
- Follow-up: "Add Czech Wikipedia, then rank by volume using the already downloaded data."
- "Compare intermittent fasting in Polish and Czech Wikipedia over the last two years."
- "We build a language-learning app. Compare learning English in Polish, Czech and Ukrainian Wikipedia; which audiences should we study next?"
- Held-out: "Compare interest in chess in English and German Wikipedia for 2024-2025."

Pass criteria: discover correct scope without invented IDs; retain missing audiences; run the full pipeline; create a one-page PDF; ground numbers in metrics; explain scope/quality limits; give an appropriate next product check; reuse cache for follow-ups. A sensible clarification or evidence-insufficient outcome is a valid result, not a reason to substitute a different concept.

Record actual model identity, prompt, commands/tool results, response, output files, duration, request counts and usage/cost when the provider exposes them. Do not infer token cost from a marketing label. Separate deterministic tests, live API tests and model behavior tests. A successful run by the development model alone does not satisfy inexpensive-model evaluation.

## OpenRouter

The optional `scripts/evaluate_openrouter.py` runner reads the installed skill and exposes a restricted CLI tool. Set `OPENROUTER_API_KEY` locally, select an exact model ID with tool support and run the supplied scenario file. API keys stay in the environment and are not written to evidence. Free availability and rate limits vary. See https://openrouter.ai/docs/guides/routing/model-variants/free and https://openrouter.ai/docs/guides/features/tool-calling .

```bash
uv run --frozen python scripts/evaluate_openrouter.py --model anthropic/claude-haiku-4.5 --scenario astronomy --out runs/openrouter-astronomy
uv run --frozen python scripts/wiki_interest.py replay --run examples/astronomy-uk-cs --out runs/replayed
```

Check the current model catalog and tool support before using that example model ID. Replay is independent of a model API and recalculates from the saved Wikimedia responses. It is a reproducibility check, not a new live study.

Development execution evidence is recorded in `examples/validation.json` when available. Do not treat planned scenarios above as completed tests.
