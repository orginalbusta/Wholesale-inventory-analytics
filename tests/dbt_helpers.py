"""Helpers for tests that build a real (small) warehouse and run dbt against it."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd
from dbt.cli.main import dbtRunner

from generator.config import DEFAULT_CONFIG_PATH, REPO_ROOT, load_config
from generator.generate import backfill, simulate_day
from ingestion.load_erp import load_erp

TRANSFORM = REPO_ROOT / "transform"


@contextmanager
def _warehouse_env(db: Path):
    previous = {k: os.environ.get(k) for k in ("WAREHOUSE", "DUCKDB_PATH")}
    os.environ.update({"WAREHOUSE": "duckdb", "DUCKDB_PATH": str(db)})
    try:
        yield
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run_dbt(root: Path, *args: str) -> dict:
    """Run a dbt command against root/warehouse.duckdb; return success + run_results."""
    db = root / "warehouse.duckdb"
    target = root / "target"
    with _warehouse_env(db):
        result = dbtRunner().invoke(
            [*args, "--project-dir", str(TRANSFORM), "--profiles-dir", str(TRANSFORM),
             "--target-path", str(target), "--log-path", str(root / "logs"), "--quiet"]
        )  # fmt: skip
    run_results = json.loads((target / "run_results.json").read_text(encoding="utf-8"))
    return {
        "success": result.success,
        "results": run_results["results"],
        "invocation_id": run_results["metadata"]["invocation_id"],
    }


def generate_and_load(root: Path, simulated_days: int = 0) -> None:
    """Backfill small data under root, add simulated days, and load it all into DuckDB."""
    cfg = load_config(DEFAULT_CONFIG_PATH, "small", root=root)
    backfill(cfg)
    for _ in range(simulated_days):
        simulate_day(cfg)
    load_new_files(root)


def simulate_and_load(root: Path) -> None:
    simulate_day(load_config(DEFAULT_CONFIG_PATH, "small", root=root))
    load_new_files(root)


def load_new_files(root: Path) -> None:
    db = root / "warehouse.duckdb"
    with _warehouse_env(db):
        load_erp(
            raw_dir=root / "data" / "raw" / "erp", duckdb_path=db, pipelines_dir=root / "pipelines"
        )


def query(root: Path, sql: str) -> pd.DataFrame:
    # dbt-duckdb keeps an in-process connection open; match its (read-write) configuration.
    with duckdb.connect(str(root / "warehouse.duckdb")) as con:
        return con.execute(sql).df()


def planted_issues(root: Path) -> pd.DataFrame:
    files = sorted((root / "data" / "_truth" / "planted_issues").glob("*.parquet"))
    return pd.concat(pd.read_parquet(f) for f in files)
