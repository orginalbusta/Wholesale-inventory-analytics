"""Incremental models after simulate-day (docs/05_roadmap.md, Phase 4).

Build a warehouse, simulate one more day, load it, run an incremental `dbt build`, and check:
    - the incremental run re-processed only recent rows (new and late-updated orders),
    - late status updates landed in fct_order_lines,
    - the incremental tables equal a full refresh of the same data.
"""

from __future__ import annotations

import pandas as pd
import pytest
from dbt_helpers import generate_and_load, query, run_dbt, simulate_and_load

INCREMENTAL_MODELS = {
    "fct_order_lines": ["order_line_id"],
    "fct_inventory_daily": ["sku", "warehouse_id", "date_day"],
}


@pytest.fixture(scope="module")
def incremental(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("dbt_incremental")
    generate_and_load(root)
    first = run_dbt(root, "build")
    before = query(root, "select order_line_id, order_status from marts.fct_order_lines")
    simulate_and_load(root)
    second = run_dbt(root, "build")
    tables = {
        name: query(root, f"select * from marts.{name}").drop(
            columns="dbt_invocation_id", errors="ignore"
        )
        for name in INCREMENTAL_MODELS
    }
    processed = query(
        root,
        f"select count(*) as n from marts.fct_order_lines where dbt_invocation_id = '{second['invocation_id']}'",
    ).at[0, "n"]
    full = run_dbt(root, "build", "--full-refresh", "--select", *INCREMENTAL_MODELS)
    return {"root": root, "first": first, "second": second, "full": full, "before": before,
            "tables": tables, "processed": processed}  # fmt: skip


def test_builds_succeed(incremental):
    for run in ("first", "second", "full"):
        assert incremental[run]["success"], run


def test_incremental_run_processes_only_recent_rows(incremental):
    total = len(incremental["tables"]["fct_order_lines"])
    assert 0 < incremental["processed"] < 0.1 * total


def test_late_status_updates_applied(incremental):
    after = incremental["tables"]["fct_order_lines"][["order_line_id", "order_status"]]
    merged = incremental["before"].merge(after, on="order_line_id", suffixes=("_before", "_after"))
    assert (merged["order_status_before"] != merged["order_status_after"]).any()


@pytest.mark.parametrize("model", list(INCREMENTAL_MODELS))
def test_incremental_equals_full_refresh(incremental, model):
    keys = INCREMENTAL_MODELS[model]
    inc = incremental["tables"][model].sort_values(keys).reset_index(drop=True)
    full = (
        query(incremental["root"], f"select * from marts.{model}")
        .drop(columns="dbt_invocation_id", errors="ignore")
        .sort_values(keys)
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(inc, full, check_exact=False, rtol=1e-9)
