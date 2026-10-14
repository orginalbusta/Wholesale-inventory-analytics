"""Tests for the dlt loaders (docs/05_roadmap.md, Phase 2).

ERP: raw row counts match the parquet files, re-running is a no-op, simulate-day loads only
the new day, and regenerated data triggers a full refresh. FRED: CSV parsing, merge
idempotency and graceful skipping are tested against a mocked HTTP layer (no network).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest
import requests

from generator.config import DEFAULT_CONFIG_PATH, load_config
from generator.generate import backfill, simulate_day
from ingestion import load_fred as fred
from ingestion.load_erp import load_erp


@pytest.fixture(autouse=True)
def _duckdb_destination(monkeypatch):
    monkeypatch.setenv("WAREHOUSE", "duckdb")


def _paths(root: Path) -> dict:
    return {
        "raw_dir": root / "data" / "raw" / "erp",
        "duckdb_path": root / "warehouse.duckdb",
        "pipelines_dir": root / "pipelines",
    }


def _parquet_rows(raw_dir: Path) -> dict[str, int]:
    return {
        d.name: sum(pq.read_metadata(f).num_rows for f in d.glob("*.parquet"))
        for d in raw_dir.iterdir()
        if d.is_dir()
    }


def _warehouse_rows(db: Path, tables) -> dict[str, int]:
    with duckdb.connect(str(db), read_only=True) as con:
        return {t: con.execute(f"select count(*) from raw_erp.{t}").fetchone()[0] for t in tables}


@pytest.fixture
def loaded(tmp_path) -> Path:
    cfg = load_config(DEFAULT_CONFIG_PATH, "small", root=tmp_path)
    backfill(cfg)
    load_erp(**_paths(tmp_path))
    return tmp_path


def test_row_counts_match_parquet(loaded):
    p = _paths(loaded)
    expected = _parquet_rows(p["raw_dir"])
    assert _warehouse_rows(p["duckdb_path"], expected) == expected


def test_reload_is_idempotent(loaded):
    p = _paths(loaded)
    before = _warehouse_rows(p["duckdb_path"], _parquet_rows(p["raw_dir"]))
    assert load_erp(**p) == {}
    assert _warehouse_rows(p["duckdb_path"], before) == before


def test_simulate_day_loads_only_the_new_day(loaded):
    p = _paths(loaded)
    before = _warehouse_rows(p["duckdb_path"], _parquet_rows(p["raw_dir"]))
    cfg = load_config(DEFAULT_CONFIG_PATH, "small", root=loaded)
    simulate_day(cfg)
    run_id = (cfg.scale.end_date + timedelta(days=1)).isoformat()

    added = load_erp(**p)
    new_files = {d.name: pq.read_metadata(d / f"{run_id}.parquet").num_rows
                 for d in p["raw_dir"].iterdir() if (d / f"{run_id}.parquet").exists()}  # fmt: skip
    assert added == new_files
    after = _warehouse_rows(p["duckdb_path"], before)
    assert {t: after[t] - before[t] for t in before if after[t] != before[t]} == new_files
    with duckdb.connect(str(p["duckdb_path"]), read_only=True) as con:
        runs = con.execute(
            "select distinct _run_id from raw_erp.sales_orders order by 1"
        ).fetchall()
    assert runs == [(run_id,), ("backfill",)]


def test_regenerated_data_triggers_full_refresh(loaded):
    p = _paths(loaded)
    backfill(load_config(DEFAULT_CONFIG_PATH, "small", seed=7, root=loaded))
    load_erp(**p)
    expected = _parquet_rows(p["raw_dir"])
    assert _warehouse_rows(p["duckdb_path"], expected) == expected
    with duckdb.connect(str(p["duckdb_path"]), read_only=True) as con:
        audit = con.execute(
            "select count(*), count(distinct file_sha256) from raw_erp.load_audit"
        ).fetchone()
    assert audit == (len(expected), len(expected))


def test_raw_types_preserved(loaded):
    with duckdb.connect(str(_paths(loaded)["duckdb_path"]), read_only=True) as con:
        types = dict(
            con.execute(
                "select column_name, data_type from information_schema.columns "
                "where table_schema = 'raw_erp' and table_name = 'purchase_orders'"
            ).fetchall()
        )
    assert types["expected_arrival_date"] == "VARCHAR"  # planted issue 8 is parsed in dbt
    assert types["updated_at"] == "TIMESTAMP"
    assert types["_extracted_at"] == "TIMESTAMP"
    assert {"_run_id", "_dlt_load_id"} <= types.keys()


# --- FRED -----------------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        pass


def _fake_csv(url, params, timeout):
    series = params["id"]
    return _FakeResponse(
        f"observation_date,{series}\n2023-01-02,\n2023-01-03,82.86\n2023-01-04,82.77\n"
    )


def test_fred_csv_load_and_merge_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(fred, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(fred.requests, "get", _fake_csv)
    db = tmp_path / "w.duckdb"
    assert fred.load_fred(duckdb_path=db, pipelines_dir=tmp_path / "p") == 3 * len(fred.FRED_SERIES)
    fred.load_fred(duckdb_path=db, pipelines_dir=tmp_path / "p")
    with duckdb.connect(str(db), read_only=True) as con:
        n, missing = con.execute(
            "select count(*), count(*) filter (where value = '') from raw_fred.observations"
        ).fetchone()
    assert n == 3 * len(fred.FRED_SERIES)
    assert missing == len(fred.FRED_SERIES)


def test_fred_unreachable_is_skipped(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(fred.requests, "get", offline)
    assert fred.load_fred(duckdb_path=tmp_path / "w.duckdb", pipelines_dir=tmp_path / "p") == 0
