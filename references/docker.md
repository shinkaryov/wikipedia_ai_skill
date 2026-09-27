# Docker execution

Run these POSIX shell commands from the skill directory. Require Docker Engine or Docker Desktop with a running daemon (`docker info`). The agent needs a terminal tool with permission to use that daemon. SKILL.md does not start a container by itself. If Docker is unavailable, use the uv setup in SKILL.md; do not install a daemon as part of a research request.

## Build and invoke

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

wiki discover --topic astronomy --languages uk cs --search-language en
# After selecting the matching QID from discovery:
wiki run --qid Q333 --languages uk cs --start 2024-01 --end 2025-12 --out runs/astronomy-01
wiki revise --run runs/astronomy-01 --criterion volume --offline --out runs/astronomy-02
```

Use `wiki` in place of `python scripts/wiki_interest.py` throughout the workflow. Define the function again when the terminal does not retain shell state. Set `WIKIMEDIA_USER_AGENT` on the host to identify the application and provide your contact for regular/public use. Do not set it to an empty string.

Keep both mounts at the same container paths for follow-ups: manifests record absolute cache paths. Mounts retain downloaded responses and all outputs after the container exits. Map paths returned as `/app/runs/...` to the host's `./runs/...` when opening or linking artifacts. Each study includes `brief.pdf`, `brief.md`, `trend.png`, `trend.svg`, `monthly.csv`, `metrics.json`, `manifest.json`, and source evidence. Use a fresh output directory for each run.

## Offline reproduction

After building once, this single smoke check recomputes a bundled study without network access or an existing cache:

```bash
mkdir -p runs
docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$(pwd)/runs,target=/app/runs" \
  wiki-interest-research:local \
  replay --run examples/astronomy-uk-cs --out runs/docker-replay-01
```

Check the JSON status and open `runs/docker-replay-01/brief.pdf`. Replay validates source checksums and recalculates from saved responses. To replay a shared study, place its complete directory (including `sources/`) under the host's `runs/`, and use `--run runs/<study>` instead. To move a native run into Docker, prefer replay; a native manifest may point to a host-only cache path.

## Reproducibility boundaries

Python 3.12.14 and uv 0.12.18 images are pinned to immutable multi-platform manifest digests. Dependencies come from `uv.lock` using `uv sync --frozen`; runtime execution does not install packages. Build requires access to the image registries and PyPI. The image includes source code and example evidence; local environments, caches and study outputs are excluded from the build context.

Record the source revision, image ID, platform, run manifest and source bundle when sharing a result. For comparisons on the same architecture, add `--platform linux/amd64` to both build and run (emulation may be required on ARM). Live API responses and relative date windows can change: use explicit dates and replay the saved evidence for repeatable calculations. PDF bytes are not promised identical because document metadata may differ.

The Docker build and container smoke check have not been executed in the authoring environment because Docker is unavailable. Registry digests were resolved successfully. Earlier Python and agent evaluations are historical evidence for the CLI, not validation of this container.

Reference: https://docs.astral.sh/uv/guides/integration/docker/
