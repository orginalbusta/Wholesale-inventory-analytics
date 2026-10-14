"""Tests for the synthetic data generator (docs/05_roadmap.md, Phase 1).

A `small` backfill is generated once into a temp directory and shared by most tests.
They check the generator's invariants: determinism, volumes, a ledger that never goes
negative, the business patterns the platform must find (Pareto revenue, seasonality,
stockouts, dead stock), planted data-quality issues, and simulate-day behavior.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from generator.config import DEFAULT_CONFIG_PATH, REPO_ROOT, FxTable, load_config
from generator.generate import backfill, simulate_day, simulate_through

TOLERANCE = 0.25


def _cfg(root: Path, scale: str = "small"):
    return load_config(DEFAULT_CONFIG_PATH, scale, root=root)


def _read(root: Path, table: str) -> pd.DataFrame:
    files = sorted((root / "data" / "raw" / "erp" / table).glob("*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _canonical_sku(raw: pd.Series) -> pd.Series:
    s = raw.str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    return s.str[:3] + "-" + s.str[3:6] + "-" + s.str[6:]


def _latest_orders(root: Path) -> pd.DataFrame:
    orders = _read(root, "sales_orders")
    return orders.sort_values("updated_at").drop_duplicates("order_id", keep="last")


@pytest.fixture(scope="session")
def small(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("small")
    backfill(_cfg(root))
    return root


@pytest.fixture(scope="session")
def revenue_lines(small) -> pd.DataFrame:
    orders = _latest_orders(small)
    lines = _read(small, "sales_order_lines").merge(
        orders[["order_id", "order_date", "status"]], on="order_id"
    )
    products = _read(small, "products")
    lines["canonical_sku"] = _canonical_sku(lines["sku"])
    lines = lines.merge(
        products[["sku"]].assign(known=True),
        left_on="canonical_sku",
        right_on="sku",
        how="left",
        suffixes=("", "_p"),
    )
    lines["revenue"] = lines["quantity_fulfilled"] * lines["unit_price_usd"]
    return lines[(lines["quantity"] > 0) & (lines["status"] != "cancelled")]


# --- Determinism and volumes --------------------------------------------------------------


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((root / "data").rglob("*"))
        if p.is_file()
    }


def test_deterministic_output(small, tmp_path):
    backfill(_cfg(tmp_path))
    assert _hash_tree(small) == _hash_tree(tmp_path)


def test_different_seed_changes_output(small, tmp_path):
    cfg = load_config(DEFAULT_CONFIG_PATH, "small", seed=7, root=tmp_path)
    backfill(cfg)
    assert _hash_tree(small) != _hash_tree(tmp_path)


def test_volumes_within_tolerance(small):
    cfg = _cfg(small)
    s = cfg.scale
    orders = _latest_orders(small)
    lines = _read(small, "sales_order_lines")
    assert abs(len(orders) / s.target_orders - 1) <= TOLERANCE
    assert abs(len(lines) / s.target_order_lines - 1) <= TOLERANCE
    assert len(_read(small, "products")) == s.n_skus
    assert len(_read(small, "suppliers")) == s.n_suppliers
    truth = pd.read_parquet(small / "data" / "_truth" / "customers.parquet")
    assert truth["duplicate_of_customer_id"].isna().sum() == s.n_customers


# --- Ledger and fulfillment invariants -----------------------------------------------------


def test_true_inventory_never_negative(small):
    mv = _read(small, "inventory_movements").sort_values("movement_id")
    running = mv.groupby(["warehouse_id", "sku"])["quantity"].cumsum()
    assert running.min() >= 0


def test_movement_ids_follow_timestamps(small):
    mv = _read(small, "inventory_movements").sort_values("movement_id")
    assert mv["movement_ts"].is_monotonic_increasing


def test_fulfilled_not_more_than_ordered(small):
    lines = _read(small, "sales_order_lines")
    normal = lines[lines["quantity"] > 0]
    assert (normal["quantity_fulfilled"] >= 0).all()
    assert (normal["quantity_fulfilled"] <= normal["quantity"]).all()


def test_received_not_more_than_ordered(small):
    pol = _read(small, "purchase_order_lines").dropna(subset=["quantity_received"])
    assert (pol["quantity_received"] <= pol["quantity_ordered"]).all()


def test_ledger_matches_cycle_counts(small):
    """After each count's adjustment, the ledger balance equals the counted quantity."""
    mv = _read(small, "inventory_movements")
    counts = _read(small, "cycle_counts").sample(200, random_state=0)
    for row in counts.itertuples():
        cutoff = pd.Timestamp(row.count_date) + timedelta(hours=19, minutes=59)
        balance = mv[
            (mv["sku"] == row.sku)
            & (mv["warehouse_id"] == row.warehouse_id)
            & (mv["movement_ts"] <= cutoff)
        ]["quantity"].sum()
        assert balance == pytest.approx(row.counted_qty)


def test_po_costs_reconcile_with_fx_seed(small):
    """unit_cost_local / FX rate for the order month = product cost in effect that day.

    dbt converts PO costs back to USD with the same FX seed, so this must hold for every line.
    """
    fx = FxTable(_cfg(small))
    pos = _read(small, "purchase_orders").drop_duplicates("po_id")
    pol = _read(small, "purchase_order_lines").drop_duplicates("po_line_id")
    lines = pol.merge(pos[["po_id", "order_date", "currency"]], on="po_id")
    lines["as_of"] = pd.to_datetime(lines["order_date"]) + timedelta(hours=20)
    hist = _read(small, "product_price_history")[["sku", "changed_at", "unit_cost_usd"]]
    matched = pd.merge_asof(
        lines.sort_values("as_of"),
        hist.sort_values("changed_at"),
        left_on="as_of",
        right_on="changed_at",
        by="sku",
    )
    assert matched["unit_cost_usd"].notna().all(), "every PO line needs a cost in effect"
    rates = [
        fx.rate(pd.Timestamp(d).date(), c)
        for d, c in zip(matched["order_date"], matched["currency"], strict=True)
    ]
    usd = matched["unit_cost_local"] / np.array(rates)
    assert np.allclose(usd, matched["unit_cost_usd"], atol=0.01)


# --- Business patterns the platform must find -----------------------------------------------


def test_stockouts_and_dead_stock_exist(small, revenue_lines):
    short = revenue_lines[revenue_lines["quantity_fulfilled"] < revenue_lines["quantity"]]
    assert len(short) > 0.01 * len(revenue_lines), "expected stockouts on a share of lines"

    mv = _read(small, "inventory_movements")
    on_hand = mv.groupby("sku")["quantity"].sum()
    last_sale = mv[mv["movement_type"] == "sale"].groupby("sku")["movement_ts"].max()
    cutoff = mv["movement_ts"].max() - timedelta(days=180)
    stale = last_sale.reindex(on_hand.index)
    dead = on_hand[(on_hand > 0) & (stale.isna() | (stale < cutoff))]
    assert len(dead) >= 3, "expected some dead stock"


def test_pareto_revenue_concentration(revenue_lines):
    by_sku = revenue_lines[revenue_lines["known"].notna()].groupby("canonical_sku")["revenue"].sum()
    by_sku = by_sku.sort_values(ascending=False)
    top = by_sku.head(round(0.2 * len(by_sku))).sum() / by_sku.sum()
    assert 0.70 <= top <= 0.85, f"top 20% of SKUs hold {top:.1%} of revenue"


def test_seasonality_visible(small, revenue_lines):
    truth = pd.read_parquet(small / "data" / "_truth" / "sku_demand_params.parquet")
    cats = truth.set_index("sku")["category"]
    lines = revenue_lines.assign(
        category=revenue_lines["canonical_sku"].map(cats),
        month=pd.to_datetime(revenue_lines["order_date"]).dt.strftime("%Y-%m"),
    )
    rev = lines.groupby(["category", "month"])["revenue"].sum()
    assert rev["Jewelry Components", "2025-11"] > 1.3 * rev["Jewelry Components", "2025-07"]
    assert rev["Decor & Landscape", "2026-04"] > 1.5 * rev["Decor & Landscape", "2025-07"]


def test_quoted_lead_times_are_optimistic(small):
    po = (
        _read(small, "purchase_orders")
        .sort_values("updated_at")
        .drop_duplicates("po_id", keep="last")
    )
    po = po[po["actual_arrival_date"].notna()]
    expected = pd.to_datetime(po["expected_arrival_date"], format="mixed")
    late = (pd.to_datetime(po["actual_arrival_date"]) - expected).dt.days > 3
    assert 0.2 < late.mean() < 0.8


def test_gem_show_orders_only_in_show_windows(small):
    orders = _latest_orders(small)
    shows = pd.read_csv(
        REPO_ROOT / "transform" / "seeds" / "gem_show_calendar.csv",
        parse_dates=["start_date", "end_date"],
    )
    show_orders = orders[orders["channel"] == "gem_show"]
    assert len(show_orders) > 0
    dates = pd.to_datetime(show_orders["order_date"])
    in_window = np.zeros(len(dates), dtype=bool)
    for s in shows.itertuples():
        in_window |= (
            (dates >= s.start_date)
            & (dates <= s.end_date)
            & (show_orders["warehouse_id"] == s.warehouse_id)
        ).to_numpy()
    assert in_window.all()


# --- Planted data-quality issues ----------------------------------------------------------


@pytest.fixture(scope="session")
def issues(small) -> pd.DataFrame:
    return pd.read_parquet(small / "data" / "_truth" / "planted_issues" / "backfill.parquet")


def _rate(issues: pd.DataFrame, issue_no: int, denominator: int) -> float:
    return (issues["issue_no"] == issue_no).sum() / denominator


def test_planted_issues_at_configured_rates(small, issues):
    rates = _cfg(small).planted_issues
    n_lines = len(_read(small, "sales_order_lines"))
    n_orders = len(_latest_orders(small))
    checks = {
        2: (rates["inconsistent_category_labels"], len(_read(small, "products"))),
        3: (rates["sku_code_variants"], n_lines),
        4: (rates["reextracted_duplicate_orders"], n_orders),
        6: (rates["negative_quantity_returns"], n_lines),
        7: (rates["bad_or_null_emails"], len(_read(small, "customers"))),
        8: (rates["mixed_date_formats"], len(_read(small, "purchase_orders"))),
        9: (rates["orphan_order_lines"], n_lines),
    }
    for issue_no, (rate, denominator) in checks.items():
        observed = _rate(issues, issue_no, denominator)
        assert 0.3 * rate <= observed <= 3 * rate, f"issue {issue_no}: {observed:.4f} vs {rate}"
    assert (issues["issue_no"] == 1).any(), "duplicate customers"
    assert (issues["issue_no"] == 10).any(), "big-miss cycle counts"


def test_planted_issue_records_look_right(small, issues):
    def ids(n):
        return set(issues.loc[issues["issue_no"] == n, "record_id"])

    products = _read(small, "products")
    mapping = pd.read_csv(REPO_ROOT / "transform" / "seeds" / "category_mapping.csv")
    normalized = products["category"].str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    assert normalized.isin(mapping["raw_category_normalized"]).all(), "every label must be mappable"
    assert (
        not products.loc[products["sku"].isin(ids(2)), "category"].isin(mapping["category"]).any()
    )

    lines = _read(small, "sales_order_lines").set_index("order_line_id")
    canonical = set(products["sku"])
    variants = lines.loc[list(ids(3)), "sku"]
    assert not variants.isin(canonical).any() and _canonical_sku(variants).isin(canonical).all()
    assert (lines.loc[list(ids(6)), "quantity"] < 0).all()
    orphans = lines.loc[list(ids(9))]
    assert not _canonical_sku(orphans["sku"]).isin(canonical).any()
    assert (orphans["quantity_fulfilled"] == 0).all()

    orders = _read(small, "sales_orders")
    assert orders["order_id"].duplicated().sum() == len(ids(4))

    customers = _read(small, "customers").set_index("customer_id")
    bad = customers.loc[list(ids(7)), "contact_email"]
    assert bad.isna().any() and not bad.dropna().str.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]+").any()

    po = _read(small, "purchase_orders").set_index("po_id")
    assert po.loc[list(ids(8)), "expected_arrival_date"].str.fullmatch(r"\d{2}/\d{2}/\d{4}").all()
    others = po.drop(index=list(ids(8)))["expected_arrival_date"]
    assert others.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()

    dup_truth = pd.read_parquet(small / "data" / "_truth" / "customers.parquet").dropna(
        subset=["duplicate_of_customer_id"]
    )
    for row in dup_truth.itertuples():
        assert customers.at[row.customer_id, "contact_email"] == customers.at[
            row.duplicate_of_customer_id, "contact_email"
        ] or (row.customer_id in ids(7) or row.duplicate_of_customer_id in ids(7))


# --- simulate-day -------------------------------------------------------------------------


def test_extending_horizon_does_not_change_history(small):
    cfg = _cfg(small)
    end = cfg.scale.end_date
    *_, sim_a = simulate_through(cfg, end)
    *_, sim_b = simulate_through(cfg, end + timedelta(days=1))
    b = sim_b.movements[sim_b.movements["movement_ts"] < pd.Timestamp(end + timedelta(days=1))]
    pd.testing.assert_frame_equal(sim_a.movements.reset_index(drop=True), b.reset_index(drop=True))


def test_simulate_day_appends_one_day(small, tmp_path):
    shutil.copytree(small / "data", tmp_path / "data")
    cfg = _cfg(tmp_path)
    simulate_day(cfg)
    day = cfg.scale.end_date + timedelta(days=1)
    run = day.isoformat()
    raw = tmp_path / "data" / "raw" / "erp"

    moves = pd.read_parquet(raw / "inventory_movements" / f"{run}.parquet")
    assert (moves["movement_ts"].dt.date == day).all()
    orders = pd.read_parquet(raw / "sales_orders" / f"{run}.parquet")
    assert (orders["updated_at"].dt.date == day).all()
    assert (orders["order_date"] == day).any(), "new orders"
    assert (orders["order_date"] < day).any(), "late-arriving status updates to older orders"
    assert not (raw / "warehouses" / f"{run}.parquet").exists()

    state = (tmp_path / "data" / "raw" / "_state.json").read_text()
    assert run in state
    simulate_day(cfg)
    assert (raw / "sales_orders" / f"{(day + timedelta(days=1)).isoformat()}.parquet").exists()
