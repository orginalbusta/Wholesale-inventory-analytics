# Runtime image for the Dagster stack: `docker compose up` runs the webserver and the daemon from it.
FROM python:3.12-slim

# Same uv release used to write uv.lock, pinned so image builds are reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    DAGSTER_HOME=/app/.dagster_home \
    DUCKDB_PATH=/app/warehouse/craftstones.duckdb \
    WAREHOUSE=duckdb

# Dependencies first so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
# dbt parse writes transform/target/manifest.json, which the Dagster code location reads at startup.
RUN uv sync --frozen --no-dev \
    && dbt deps --project-dir transform --profiles-dir transform \
    && dbt parse --project-dir transform --profiles-dir transform \
    && mkdir -p "$DAGSTER_HOME" \
    && cp orchestration/dagster.yaml "$DAGSTER_HOME/dagster.yaml"

EXPOSE 3000
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-m", "orchestration.craftstones_dagster.definitions"]
