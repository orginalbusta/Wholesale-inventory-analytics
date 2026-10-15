"""Cross-check dbt staging against the generator's ground truth (docs/05_roadmap.md, Phase 3).

Builds a fresh `small` warehouse (backfill + one simulate-day, so late-arriving updates are
included), runs `dbt build`, then checks every planted data-quality issue recorded in
data/_truth/planted_issues/ is either fixed in staging or caught by a dbt test.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import duckdb
import pandas as pd
import pytest
from dbt.cli.main import dbtRunner

from generator.config import DEFAULT_CONFIG_PATH, REPO_ROOT, load_config
from generator.generate import backfill, simulate_day
from ingestion.load_erp import load_erp

TRANSFORM = REPO_ROOT / "transform"
EXPECTED_WARNINGS = {
    "assert_no_duplicate_customer_emails": 1,
    "dbt_expectations_expect_column_values_to_match_regex_stg_erp__customers_contact_email": 7,
    "relationships_stg_erp__sales_order_lines_sku": 9,
    "dbt_expectations_expect_column_values_to_be_between_stg_erp__cycle_counts_variance_pct": 10,
}


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("dbt")
    cfg = load_config(DEFAULT_CONFIG_PATH, "small", root=root)
    backfill(cfg)
    simulate_day(cfg)
    db = root / "warehouse.duckdb"
    previous = {k: os.environ.get(k) for k in ("WAREHOUSE", "DUCKDB_PATH")}
    os.environ.update({"WAREHOUSE": "duckdb", "DUCKDB_PATH": str(db)})
    try:
        load_erp(
            raw_dir=root / "data" / "raw" / "erp", duckdb_path=db, pipelines_dir=root / "pipelines"
        )
        target = root / "target"
        result = dbtRunner().invoke(
            ["build", "--project-dir", str(TRANSFORM), "--profiles-dir", str(TRANSFORM),
             "--target-path", str(target), "--log-path", str(root / "logs"), "--quiet"]
        )  # fmt: skip
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    run_results = json.loads((target / "run_results.json").read_text(encoding="utf-8"))
    issues = pd.concat(
        pd.read_parquet(f)
        for f in sorted((root / "data" / "_truth" / "planted_issues").glob("*.parquet"))
    )
    return {
        "root": root,
        "db": db,
        "success": result.success,
        "results": run_results["results"],
        "issues": issues,
    }


def _query(built, sql: str) -> pd.DataFrame:
    # dbt-duckdb keeps an in-process connection open; match its (read-write) configuration.
    with duckdb.connect(str(built["db"])) as con:
        return con.execute(sql).df()


def _ids(built, issue_no: int) -> list[str]:
    issues = built["issues"]
    return sorted(set(issues.loc[issues["issue_no"] == issue_no, "record_id"]))


def _in(ids) -> str:
    return "(" + ", ".join(f"'{i}'" for i in ids) + ")"


def test_build_succeeds_with_only_expected_warnings(built):
    assert built["success"]
    statuses = {r["unique_id"]: (r["status"], r.get("failures")) for r in built["results"]}
    assert not [u for u, (s, _) in statuses.items() if s in ("error", "fail")]
    warned = {u for u, (s, _) in statuses.items() if s == "warn"}
    for prefix in EXPECTED_WARNINGS:
        assert any(prefix in u for u in warned), f"expected a warning from {prefix}"
    assert len(warned) == len(EXPECTED_WARNINGS)


def _failures(built, prefix: str) -> int:
    return next(r["failures"] for r in built["results"] if prefix in r["unique_id"])


def test_issue_1_duplicate_customers_flagged(built):
    truth = pd.read_parquet(built["root"] / "data" / "_truth" / "customers.parquet")
    pairs = truth.dropna(subset=["duplicate_of_customer_id"])
    stg = _query(
        built, "select customer_id, contact_email from staging.stg_erp__customers"
    ).set_index("customer_id")
    bad_email = set(_ids(built, 7))
    intact = [
        (d, o) for d, o in zip(pairs["customer_id"], pairs["duplicate_of_customer_id"], strict=True)
        if d not in bad_email and o not in bad_email
    ]  # fmt: skip
    assert intact, "expected at least one duplicate pair with intact emails"
    for dup, orig in intact:
        assert stg.at[dup, "contact_email"] == stg.at[orig, "contact_email"]
    assert _failures(built, "assert_no_duplicate_customer_emails") >= len(intact)


def test_issue_2_categories_mapped(built):
    truth = pd.read_parquet(built["root"] / "data" / "_truth" / "sku_demand_params.parquet")
    stg = _query(built, "select sku, category from staging.stg_erp__products")
    merged = truth.merge(stg, on="sku", suffixes=("_truth", "_stg"))
    assert len(merged) == len(truth)
    assert (merged["category_truth"] == merged["category_stg"]).all()
    assert len(_ids(built, 2)) > 0


def test_issue_3_sku_variants_normalized(built):
    ids = _ids(built, 3)
    df = _query(
        built,
        f"""select l.sku_raw, l.sku, p.sku is not null as known
            from staging.stg_erp__sales_order_lines l
            left join staging.stg_erp__products p using (sku)
            where l.order_line_id in {_in(ids)}""",
    )
    assert len(df) == len(ids)
    assert (df["sku_raw"] != df["sku"]).all() and df["known"].all()


def test_issue_4_reextracted_duplicates_removed(built):
    df = _query(
        built,
        """with latest as (
               select order_id, arg_max(status, updated_at) as latest_status
               from raw_erp.sales_orders group by 1
           )
           select count(*) as n, count(distinct s.order_id) as n_distinct,
                  count(*) filter (where s.order_status <> l.latest_status) as wrong_status
           from staging.stg_erp__sales_orders s join latest l using (order_id)""",
    )
    assert df.at[0, "n"] == df.at[0, "n_distinct"]
    assert df.at[0, "wrong_status"] == 0
    raw_dupes = _query(
        built, "select count(*) - count(distinct order_id) as d from raw_erp.sales_orders"
    ).at[0, "d"]
    assert raw_dupes > 0, "raw should still hold duplicates and later versions"
    assert len(_ids(built, 4)) > 0


def test_issue_5_late_status_updates_applied(built):
    late = built["issues"][built["issues"]["issue_no"] == 5]
    assert len(late) > 0
    run_day = datetime.fromisoformat(late["run_id"].iloc[0]).date()
    df = _query(
        built,
        f"""select order_id, order_date, cast(updated_at as date) as updated_date
            from staging.stg_erp__sales_orders where order_id in {_in(late["record_id"])}""",
    )
    assert (df["order_date"].dt.date < run_day).all()
    assert (df["updated_date"] == pd.Timestamp(run_day)).all()


def test_issue_6_negative_lines_become_returns(built):
    ids = _ids(built, 6)
    df = _query(
        built,
        f"select is_return_line, quantity from staging.stg_erp__sales_order_lines where order_line_id in {_in(ids)}",
    )
    assert len(df) == len(ids) and df["is_return_line"].all() and (df["quantity"] > 0).all()
    n_returns = _query(
        built, "select count(*) as n from staging.stg_erp__sales_order_lines where is_return_line"
    ).at[0, "n"]
    assert n_returns == len(ids)


def test_issue_7_bad_emails_flagged(built):
    ids = set(_ids(built, 7))
    df = _query(
        built, "select customer_id, contact_email, is_email_valid from staging.stg_erp__customers"
    )
    bad = df[df["customer_id"].isin(ids)]
    assert (bad["contact_email"].isna() | (bad["is_email_valid"] == False)).all()  # noqa: E712
    good = df[~df["customer_id"].isin(ids)]
    assert good["is_email_valid"].all()
    malformed = int((bad["is_email_valid"] == False).sum())  # noqa: E712
    assert _failures(built, "match_regex_stg_erp__customers_contact_email") == malformed


def test_issue_8_mixed_dates_parsed(built):
    ids = _ids(built, 8)
    df = _query(
        built,
        f"""select expected_arrival_date_raw, expected_arrival_date
            from staging.stg_erp__purchase_orders where po_id in {_in(ids)}""",
    )
    assert len(df) == len(ids)
    parsed = pd.to_datetime(df["expected_arrival_date_raw"], format="%m/%d/%Y")
    assert (parsed == pd.to_datetime(df["expected_arrival_date"])).all()
    assert (
        _query(
            built,
            "select count(*) as n from staging.stg_erp__purchase_orders where expected_arrival_date is null",
        ).at[0, "n"]
        == 0
    )


def test_issue_9_orphan_lines_caught(built):
    ids = _ids(built, 9)
    df = _query(
        built,
        f"""select p.sku is null as orphan from staging.stg_erp__sales_order_lines l
            left join staging.stg_erp__products p using (sku) where l.order_line_id in {_in(ids)}""",
    )
    assert len(df) == len(ids) and df["orphan"].all()
    assert _failures(built, "relationships_stg_erp__sales_order_lines_sku") == len(ids)


def test_issue_10_big_miss_counts_caught(built):
    ids = _ids(built, 10)
    df = _query(
        built,
        f"select variance_pct from staging.stg_erp__cycle_counts where count_id in {_in(ids)}",
    )
    assert len(df) == len(ids) and (df["variance_pct"] < -0.15).all()
    assert _failures(built, "stg_erp__cycle_counts_variance_pct") == len(ids)


def test_snapshots_built(built):
    n = _query(built, "select count(*) as n from snapshots.snap_products").at[0, "n"]
    assert n >= _query(built, "select count(*) as n from staging.stg_erp__products").at[0, "n"]


def test_staging_has_no_planted_issues_left_unexplained(built):
    """Every issue number the generator plants is covered by a test above."""
    assert set(built["issues"]["issue_no"]) == set(range(1, 11))
