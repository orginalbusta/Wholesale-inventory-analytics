"""Slowly changing reference attributes: product cost/price and customer terms over time.

These changes are what the dbt snapshots (`snap_products`, `snap_customers`) and the
`product_price_history` table capture:
    - ~2% of SKUs per month get a cost change (larger for FX-exposed origins);
      list price follows 0-30 days later at the SKU's markup.
    - ~1% of customers per month change credit terms; sales reps are reassigned rarely.

Each day draws from its own random stream, so extending the horizon never rewrites history.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from generator.config import Config
from generator.randomness import day_rng
from generator.reference import CREDIT_TERMS, SALES_REPS, Reference

DAYS_PER_MONTH = 30.44


@dataclass
class Timelines:
    days: pd.DatetimeIndex  # simulation horizon, one entry per day
    unit_cost: np.ndarray  # [day, sku] cost in effect at the end of each day
    list_price: np.ndarray  # [day, sku]
    price_events: pd.DataFrame  # sku_pos, day_index, changed_at, unit_cost_usd, list_price_usd
    customer_events: pd.DataFrame  # cust_pos, day_index, changed_at, credit_terms, sales_rep_id


def build_price_path(cfg: Config, ref: Reference, days: pd.DatetimeIndex):
    products = ref.products
    n, t_count = len(products), len(days)
    markup = products["markup"].to_numpy()
    fx_exposed = products["supplier_pos"].map(ref.suppliers["currency"]).to_numpy() != "USD"
    cost = products["unit_cost_usd"].to_numpy().astype(float).copy()
    price = products["list_price_usd"].to_numpy().astype(float).copy()
    cost_path = np.empty((t_count, n))
    price_path = np.empty((t_count, n))
    pending: dict[int, list[int]] = {}
    events = []
    p_change = cfg.reference_changes["cost_change_monthly_rate"] / DAYS_PER_MONTH
    # A product's cost can only change once it exists in the ERP.
    created = ref.product_created_ts.astype("datetime64[D]")

    for t in range(t_count):
        rng = day_rng(cfg.seed, "prices", t)
        u = rng.random(n)
        pct = np.where(fx_exposed, rng.uniform(0.05, 0.15, n), rng.uniform(0.03, 0.08, n))
        sign = np.where(rng.random(n) < 0.7, 1.0, -1.0)
        lag = rng.integers(0, 31, n)

        changed = np.flatnonzero((u < p_change) & (created <= days[t].to_datetime64()))
        for i in changed:
            cost[i] = round(cost[i] * (1 + sign[i] * pct[i]), 2)
            events.append((i, t, days[t] + pd.Timedelta(hours=9), cost[i], price[i]))
            if lag[i] == 0:
                price[i] = round(cost[i] * markup[i], 2)
                events.append(
                    (i, t, days[t] + pd.Timedelta(hours=9, minutes=30), cost[i], price[i])
                )
            else:
                pending.setdefault(t + int(lag[i]), []).append(i)
        for i in pending.pop(t, []):
            price[i] = round(cost[i] * markup[i], 2)
            events.append((i, t, days[t] + pd.Timedelta(hours=9, minutes=30), cost[i], price[i]))

        cost_path[t] = cost
        price_path[t] = price

    price_events = pd.DataFrame(
        events, columns=["sku_pos", "day_index", "changed_at", "unit_cost_usd", "list_price_usd"]
    )
    return cost_path, price_path, price_events


def build_customer_events(cfg: Config, ref: Reference, days: pd.DatetimeIndex) -> pd.DataFrame:
    customers = ref.customers
    n = len(customers)
    created = pd.to_datetime(customers["created_date"]).to_numpy()
    is_dup = customers["duplicate_of_pos"].to_numpy() >= 0
    terms = customers["credit_terms"].to_numpy().astype(object).copy()
    reps = customers["sales_rep_id"].to_numpy().astype(object).copy()
    p_terms = cfg.reference_changes["credit_terms_change_monthly_rate"] / DAYS_PER_MONTH
    p_rep = cfg.reference_changes["sales_rep_change_monthly_rate"] / DAYS_PER_MONTH
    events = []

    for t, day in enumerate(days):
        rng = day_rng(cfg.seed, "customer_changes", t)
        u_terms, u_rep = rng.random(n), rng.random(n)
        new_terms_idx = rng.integers(0, len(CREDIT_TERMS) - 1, n)
        new_rep_idx = rng.integers(0, len(SALES_REPS) - 1, n)
        # Duplicate records are stale copies nobody maintains, so they never change.
        eligible = (created < day.to_datetime64()) & ~is_dup
        for c in np.flatnonzero(eligible & ((u_terms < p_terms) | (u_rep < p_rep))):
            if u_terms[c] < p_terms:
                options = [x for x in CREDIT_TERMS if x != terms[c]]
                terms[c] = options[new_terms_idx[c] % len(options)]
            if u_rep[c] < p_rep:
                options = [x for x in SALES_REPS if x != reps[c]]
                reps[c] = options[new_rep_idx[c] % len(options)]
            events.append((c, t, day + pd.Timedelta(hours=11), terms[c], reps[c]))

    return pd.DataFrame(
        events, columns=["cust_pos", "day_index", "changed_at", "credit_terms", "sales_rep_id"]
    )


def build_timelines(cfg: Config, ref: Reference, horizon_end) -> Timelines:
    days = pd.date_range(cfg.scale.start_date, horizon_end, freq="D")
    cost_path, price_path, price_events = build_price_path(cfg, ref, days)
    customer_events = build_customer_events(cfg, ref, days)
    return Timelines(days, cost_path, price_path, price_events, customer_events)
