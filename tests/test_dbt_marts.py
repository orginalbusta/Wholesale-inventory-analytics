"""Marts recover the generator's ground truth (docs/05_roadmap.md, Phase 4).

The generator knows the true supplier lead-time distributions, duplicate customers, demand
weights and expected demand. If the marts are right, the analysis should find them again.
"""

from __future__ import annotations

import pandas as pd
from dbt_helpers import query


def _truth(built, name: str) -> pd.DataFrame:
    return pd.read_parquet(built["root"] / "data" / "_truth" / f"{name}.parquet")


def test_full_build_has_no_errors(built):
    assert built["success"]
    assert not [r["unique_id"] for r in built["results"] if r["status"] in ("error", "fail")]


def test_supplier_lead_times_recovered(built):
    est = query(
        built["root"],
        "select supplier_id, lead_time_mean_days, received_po_count from marts.mart_supplier_performance",
    )
    truth = _truth(built, "supplier_lead_times")
    merged = est.merge(truth, on="supplier_id")
    merged = merged[merged["received_po_count"] >= 20]
    error = merged["lead_time_mean_days"] / merged["true_lead_time_mean_days"] - 1
    assert len(merged) >= 10
    assert error.abs().mean() < 0.10, error.describe()
    assert error.abs().max() < 0.35, error.describe()


def test_quoted_lead_times_are_optimistic(built):
    perf = query(
        built["root"],
        "select supplier_id, quoted_vs_actual_gap_days from marts.mart_supplier_performance",
    )
    assert (perf["quoted_vs_actual_gap_days"] > 0).mean() >= 0.8


def test_lead_time_variability_recovered(built):
    """Measured lead-time variability (coefficient of variation) tracks the true lognormal
    sigma, so the reorder logic gives unreliable suppliers more safety stock.
    (On-time rate isn't the right check: it depends mostly on lead-time length.)"""
    perf = query(
        built["root"],
        "select supplier_id, lead_time_std_days / lead_time_mean_days as cv"
        " from marts.mart_supplier_performance where received_po_count >= 10",
    )
    merged = perf.merge(_truth(built, "supplier_lead_times"), on="supplier_id")
    assert merged["cv"].corr(merged["true_lead_time_sigma"]) > 0.7
    by_reliability = merged.groupby("is_unreliable")["cv"].mean()
    assert by_reliability[True] > by_reliability[False]


def test_duplicate_customers_resolved_exactly(built):
    found = query(
        built["root"],
        "select customer_id, canonical_customer_id from intermediate.int_customers__deduplicated where is_duplicate_record",
    )
    truth = _truth(built, "customers").dropna(subset=["duplicate_of_customer_id"])
    assert dict(zip(found["customer_id"], found["canonical_customer_id"], strict=True)) == dict(
        zip(truth["customer_id"], truth["duplicate_of_customer_id"], strict=True)
    )
    n_customers = query(built["root"], "select count(*) as n from marts.dim_customers").at[0, "n"]
    assert n_customers == len(_truth(built, "customers")) - len(truth)


def test_a_class_matches_true_demand_weights(built):
    dbt_a = set(
        query(built["root"], "select sku from marts.dim_products where abc_class = 'A'")["sku"]
    )
    truth = _truth(built, "sku_demand_params")
    true_a = set(truth.loc[truth["is_a_class_truth"], "sku"])
    assert len(dbt_a & true_a) / len(dbt_a) >= 0.7


def test_true_demand_matches_expected_demand(built):
    """Demand in dbt (incl. unfilled) should track the generator's expected units."""
    dbt_total = query(
        built["root"],
        "select sum(ordered_qty) as q from intermediate.int_sku_demand__daily where date_day <= date '2026-09-30'",
    ).at[0, "q"]
    expected = _truth(built, "expected_demand_daily")
    expected_total = (expected["expected_units"] + expected["expected_show_units"]).sum()
    assert abs(dbt_total / expected_total - 1) < 0.15


def test_business_problems_are_visible(built):
    """The simulated baseline policy should leave measurable problems for the platform to fix."""
    root = built["root"]
    health = query(
        root,
        "select sum(on_hand_value_usd) as total, sum(case when is_dead_stock then on_hand_value_usd end) as dead from marts.mart_inventory_health",
    )
    assert health.at[0, "dead"] > 0.02 * health.at[0, "total"]
    stockouts = query(
        root, "select sum(stockout_days) as d from marts.mart_stockouts where abc_class = 'A'"
    )
    assert stockouts.at[0, "d"] > 0
    reorder = query(
        root,
        "select count(*) filter (where reorder_now) as n from marts.mart_reorder_recommendations where abc_class = 'A'",
    )
    assert reorder.at[0, "n"] > 0
