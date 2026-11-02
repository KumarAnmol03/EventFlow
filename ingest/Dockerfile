FROM python:3.12-slim

# uv installs dependencies from the lockfile exactly (reproducible builds).
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY eventflow_ingest ./eventflow_ingest
COPY migrations ./migrations
COPY schemas ./schemas

# Run as an unprivileged user, not root.
RUN useradd --system --uid 10001 ingest
USER ingest

EXPOSE 8080
CMD ["/app/.venv/bin/uvicorn", "eventflow_ingest.api:app", "--host", "0.0.0.0", "--port", "8080"]
