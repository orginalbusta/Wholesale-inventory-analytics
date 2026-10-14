# Keep in sync with the command list in CLAUDE.md.
SCALE ?= small
TARGET ?= dev
DBT = uv run dbt --no-use-colors
DBT_ARGS = --project-dir transform --profiles-dir transform --target $(TARGET)

.PHONY: setup generate simulate-day load dbt-build all docs lint test dagster dashboard clean

setup:
	uv sync --all-groups
	$(DBT) deps --project-dir transform --profiles-dir transform
	uv run pre-commit install || true

generate:
	uv run python -m generator.generate --scale $(SCALE) --mode backfill

simulate-day:
	uv run python -m generator.generate --scale $(SCALE) --mode simulate-day

load:
	uv run python -m ingestion.load_erp
	uv run python -m ingestion.load_fred

dbt-build:
	$(DBT) build $(DBT_ARGS)

all: generate load dbt-build

docs:
	$(DBT) docs generate $(DBT_ARGS)

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run sqlfluff lint transform/models transform/tests transform/snapshots transform/macros

test:
	uv run pytest -q

dagster:
	uv run dagster dev

dashboard:
	cd dashboard && npm install && npm run sources && npm run dev

clean:
	rm -rf data/raw data/_truth warehouse/*.duckdb transform/target transform/dbt_packages transform/logs
