# Runtime image for the Dagster stack (Phase 6).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    DAGSTER_HOME=/app/.dagster_home \
    DUCKDB_PATH=/app/warehouse/craftstones.duckdb

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

COPY . .
RUN uv sync --no-dev \
    && uv run dbt deps --project-dir transform --profiles-dir transform \
    && uv run dbt parse --project-dir transform --profiles-dir transform \
    && mkdir -p "$DAGSTER_HOME"

EXPOSE 3000
CMD ["uv", "run", "dagster", "dev", "-h", "0.0.0.0", "-p", "3000"]
