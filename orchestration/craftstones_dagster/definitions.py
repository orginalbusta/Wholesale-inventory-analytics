"""Dagster code location for the Craftstones pipeline.

Asset graph (left to right is the order data flows):

    erp_extracts            generator: backfill on first run, then one extract per day through yesterday
      -> raw_erp/<table>    dlt load of the extract files (one asset per ERP table)
    raw_fred/observations   dlt load of public FRED series (no upstream; fetched from the internet)
      -> dbt models         every seed, staging/intermediate/mart model and snapshot, from the dbt manifest

dbt sources are mapped onto the raw_erp / raw_fred asset keys, so the lineage graph runs end to end
from the generator to the marts. dbt tests show up as Dagster asset checks (dagster-dbt reads them from
the manifest), and `dbt source freshness` is a separate asset check on the raw ERP tables.

Run locally with `make dagster` (UI at http://localhost:3000) or `docker compose up`.
"""

# No `from __future__ import annotations`: Dagster inspects the type hints at runtime.
import json
import os
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetCheckSpec,
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    AssetSpec,
    ConfigurableResource,
    DefaultScheduleStatus,
    Definitions,
    MaterializeResult,
    ScheduleDefinition,
    asset,
    define_asset_job,
    in_process_executor,
    multi_asset,
    multi_asset_check,
)
from dagster_dbt import (
    DagsterDbtTranslator,
    DagsterDbtTranslatorSettings,
    DbtCliResource,
    DbtProject,
    dbt_assets,
)

from generator.config import DEFAULT_CONFIG_PATH, load_config
from generator.generate import backfill, catch_up
from ingestion.load_erp import load_erp
from ingestion.load_fred import load_fred

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSFORM_DIR = REPO_ROOT / "transform"

# dbt runs with the transform/ folder as its working directory, but dlt and the Makefile resolve
# DUCKDB_PATH from the repo root. Make it absolute so every step writes to the same warehouse file.
_duckdb_path = Path(os.getenv("DUCKDB_PATH", "warehouse/craftstones.duckdb"))
if not _duckdb_path.is_absolute():
    os.environ["DUCKDB_PATH"] = str(REPO_ROOT / _duckdb_path)

dbt_project = DbtProject(project_dir=TRANSFORM_DIR, profiles_dir=TRANSFORM_DIR)
# Under `dagster dev`, (re)parse the dbt project so the manifest is never stale.
# In Docker the image builds the manifest with `dbt parse`; anywhere else (pytest, a fresh clone),
# parse once if there is no manifest yet.
dbt_project.prepare_if_dev()
if not dbt_project.manifest_path.exists():
    dbt_project.preparer.prepare(dbt_project)


def _erp_source_tables(manifest_path: Path) -> list[dict[str, Any]]:
    """The ERP source tables declared in dbt, so the raw assets always match the dbt sources."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tables = [s for s in manifest["sources"].values() if s["source_name"] == "erp"]
    return sorted(tables, key=lambda s: s["name"])


ERP_SOURCES = _erp_source_tables(dbt_project.manifest_path)
ERP_TABLES = [s["name"] for s in ERP_SOURCES]
FRESHNESS_TABLES = [
    s["name"]
    for s in ERP_SOURCES
    if (s.get("freshness") or {}).get("warn_after", {}).get("count")
    or (s.get("freshness") or {}).get("error_after", {}).get("count")
]


class PipelineConfig(ConfigurableResource):
    """Where the generator writes its files and at what scale. Tests point `root` at a temp folder."""

    root: str = str(REPO_ROOT)
    scale: str = os.getenv("SCALE", "small")  # used for the first backfill only

    @property
    def raw_erp_dir(self) -> Path:
        return Path(self.root) / "data" / "raw" / "erp"

    @property
    def pipelines_dir(self) -> Path:
        return Path(self.root) / ".dlt" / "pipelines"


# --- Generate ---------------------------------------------------------------------------------


@asset(
    group_name="generate",
    description=(
        "Synthetic ERP extract files (parquet) in data/raw/erp. On the first run this writes the "
        "full backfill; afterwards it writes one day-only extract for every day through yesterday, "
        "like a nightly ERP export. All data is fictional."
    ),
)
def erp_extracts(context: AssetExecutionContext, pipeline: PipelineConfig) -> MaterializeResult:
    cfg = load_config(DEFAULT_CONFIG_PATH, pipeline.scale, root=Path(pipeline.root))
    if not cfg.state_file.exists():
        context.log.info(f"No generator state yet: running the {pipeline.scale} backfill.")
        backfill(cfg)
    else:
        # Keep extending whatever scale the existing data was generated at (e.g. after `make all`).
        state_scale = json.loads(cfg.state_file.read_text(encoding="utf-8"))["scale"]
        cfg = load_config(DEFAULT_CONFIG_PATH, state_scale, root=Path(pipeline.root))
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    counts = catch_up(cfg, until=yesterday)
    state = json.loads(cfg.state_file.read_text(encoding="utf-8"))
    return MaterializeResult(
        metadata={
            "scale": pipeline.scale,
            "data_as_of": state["as_of_date"],
            "new_rows": sum(counts.values()),
        }
    )


# --- Ingest -----------------------------------------------------------------------------------


@multi_asset(
    group_name="ingest",
    specs=[
        AssetSpec(
            AssetKey(["raw_erp", table]),
            deps=[erp_extracts],
            description=f"raw_erp.{table}: extract files appended by dlt (ingestion/load_erp.py).",
            kinds={"dlt", "duckdb"},
        )
        for table in ERP_TABLES
    ],
)
def raw_erp(pipeline: PipelineConfig) -> Iterator[MaterializeResult]:
    """Load every extract file that isn't in the warehouse yet (dlt; idempotent)."""
    counts = load_erp(raw_dir=pipeline.raw_erp_dir, pipelines_dir=pipeline.pipelines_dir)
    for table in ERP_TABLES:
        yield MaterializeResult(
            asset_key=AssetKey(["raw_erp", table]),
            metadata={"rows_loaded": counts.get(table, 0)},
        )


@asset(
    key=AssetKey(["raw_fred", "observations"]),
    group_name="ingest",
    description=(
        "raw_fred.observations: public economic and FX series from FRED (ingestion/load_fred.py). "
        "If FRED is unreachable the load is skipped and dbt falls back to the FX seed."
    ),
    kinds={"dlt", "duckdb"},
)
def raw_fred_observations(pipeline: PipelineConfig) -> MaterializeResult:
    rows = load_fred(pipelines_dir=pipeline.pipelines_dir)
    return MaterializeResult(metadata={"rows_fetched": rows})


# --- Transform --------------------------------------------------------------------------------


class CraftstonesDbtTranslator(DagsterDbtTranslator):
    """Map dbt sources onto the raw assets above (raw_erp/<table>, raw_fred/<table>) and group
    dbt assets by layer (seeds, snapshots, staging, intermediate, marts) in the UI."""

    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        if dbt_resource_props["resource_type"] == "source":
            return AssetKey([dbt_resource_props["schema"], dbt_resource_props["name"]])
        return super().get_asset_key(dbt_resource_props)

    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str | None:
        resource_type = dbt_resource_props["resource_type"]
        if resource_type in ("seed", "snapshot"):
            return f"{resource_type}s"
        if resource_type == "model":
            return dbt_resource_props["fqn"][1]  # models/<layer>/...
        return super().get_group_name(dbt_resource_props)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=CraftstonesDbtTranslator(
        # Tests on raw sources (e.g. the planted data-quality issues) become checks on raw_erp/*.
        settings=DagsterDbtTranslatorSettings(enable_source_tests_as_checks=True)
    ),
)
def craftstones_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """`dbt build`: seeds, models, snapshots and tests. Incremental models stay incremental."""
    yield from dbt.cli(["build"], context=context).stream()


@multi_asset_check(
    specs=[
        AssetCheckSpec(
            "source_freshness",
            asset=AssetKey(["raw_erp", table]),
            description="dbt source freshness: warns after 2 days without new data, errors after 5.",
        )
        for table in FRESHNESS_TABLES
    ],
)
def raw_erp_freshness(dbt: DbtCliResource) -> Iterator[AssetCheckResult]:
    """Run `dbt source freshness` and report one result per raw ERP table that has a freshness rule."""
    invocation = dbt.cli(["source", "freshness"], raise_on_error=False).wait()
    sources_json = invocation.target_path / "sources.json"
    results = json.loads(sources_json.read_text(encoding="utf-8"))["results"]
    by_table = {r["unique_id"].rsplit(".", 1)[-1]: r for r in results}
    for table in FRESHNESS_TABLES:
        result = by_table.get(table, {})
        status = result.get("status", "missing")
        yield AssetCheckResult(
            asset_key=AssetKey(["raw_erp", table]),
            check_name="source_freshness",
            passed=status == "pass",
            severity=AssetCheckSeverity.WARN if status == "warn" else AssetCheckSeverity.ERROR,
            metadata={
                "status": status,
                "max_loaded_at": str(result.get("max_loaded_at")),
                "age_hours": round(float(result.get("max_loaded_at_time_ago_in_s", 0)) / 3600, 1),
            },
        )


# --- Jobs and schedules -----------------------------------------------------------------------

daily_pipeline_job = define_asset_job(
    "daily_pipeline_job",
    selection=AssetSelection.all(),
    description="Generate the next days of ERP extracts, load them, and run dbt build.",
)

daily_schedule = ScheduleDefinition(
    job=daily_pipeline_job,
    cron_schedule="0 6 * * *",
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,
    description="Every morning at 06:00 Pacific. Off by default; turn it on in the UI.",
)

defs = Definitions(
    assets=[erp_extracts, raw_erp, raw_fred_observations, craftstones_dbt_assets],
    asset_checks=[raw_erp_freshness],
    jobs=[daily_pipeline_job],
    schedules=[daily_schedule],
    resources={
        "pipeline": PipelineConfig(),
        "dbt": DbtCliResource(project_dir=dbt_project),
    },
    # DuckDB allows one writer at a time, so run steps one after another in a single process.
    executor=in_process_executor,
)
