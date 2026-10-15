"""Dagster code location: the asset graph is wired end to end, and materializing every asset
(generate -> load -> dbt build, plus the freshness check) succeeds on a fresh small warehouse."""

from __future__ import annotations

import os

import pytest
from dagster import AssetKey, DefaultScheduleStatus, materialize
from dagster_dbt import DbtCliResource

from orchestration.craftstones_dagster.definitions import (
    ERP_TABLES,
    PipelineConfig,
    craftstones_dbt_assets,
    daily_schedule,
    dbt_project,
    defs,
    erp_extracts,
    raw_erp,
    raw_erp_freshness,
    raw_fred_observations,
)

MART = AssetKey(["marts", "mart_reorder_recommendations"])


def test_lineage_runs_from_generator_to_marts():
    graph = defs.resolve_asset_graph()
    upstream = graph.upstream_key_iterator(MART)
    assert AssetKey("erp_extracts") in set(upstream)
    assert (
        AssetKey(["raw_erp", "sales_orders"])
        in graph.get(AssetKey(["staging", "stg_erp__sales_orders"])).parent_keys
    )
    assert (
        AssetKey(["raw_fred", "observations"])
        in graph.get(AssetKey(["staging", "stg_fred__observations"])).parent_keys
    )


def test_every_dbt_source_is_a_real_asset():
    """No dbt source should show up as an unmaterializable stub: each maps to a raw_* asset."""
    graph = defs.resolve_asset_graph()
    stubs = [
        k.to_user_string() for k in graph.get_all_asset_keys() if not graph.get(k).is_executable
    ]
    assert stubs == []
    assert len(ERP_TABLES) >= 10


def test_dbt_tests_are_asset_checks():
    checks = defs.resolve_asset_graph().asset_check_keys
    assert any(c.asset_key == MART for c in checks)
    assert any(c.name == "source_freshness" for c in checks)


def test_schedule_is_off_by_default():
    assert daily_schedule.default_status == DefaultScheduleStatus.STOPPED
    assert daily_schedule.execution_timezone == "America/Los_Angeles"


@pytest.fixture
def isolated_warehouse(tmp_path, monkeypatch):
    monkeypatch.setenv("WAREHOUSE", "duckdb")
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "warehouse.duckdb"))
    return tmp_path


def test_materialize_all_assets(isolated_warehouse):
    root = isolated_warehouse
    result = materialize(
        [erp_extracts, raw_erp, raw_fred_observations, craftstones_dbt_assets, raw_erp_freshness],
        resources={
            "pipeline": PipelineConfig(root=str(root), scale="small"),
            "dbt": DbtCliResource(project_dir=dbt_project),
        },
    )
    assert result.success
    assert (root / "warehouse.duckdb").exists()
    assert os.environ["DUCKDB_PATH"] == str(root / "warehouse.duckdb")

    materialized = {e.asset_key for e in result.get_asset_materialization_events()}
    assert {AssetKey("erp_extracts"), MART, AssetKey(["raw_erp", "sales_orders"])} <= materialized

    freshness = [
        e for e in result.get_asset_check_evaluations() if e.check_name == "source_freshness"
    ]
    # The generator catches up through yesterday, so the raw tables are fresh.
    assert freshness and all(f.passed for f in freshness)
