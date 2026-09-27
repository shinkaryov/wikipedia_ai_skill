# Immutable multi-platform manifests; versions verified against registries.
FROM ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc AS uv
FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    MPLCONFIGDIR=/tmp/matplotlib \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache
COPY scripts/ scripts/
COPY references/ references/
COPY examples/ examples/
COPY SKILL.md ./
RUN mkdir -p /app/.cache /app/runs && chown -R 1000:1000 /app/.cache /app/runs
USER 1000:1000
ENTRYPOINT ["/app/.venv/bin/python", "/app/scripts/wiki_interest.py"]
CMD ["--help"]
