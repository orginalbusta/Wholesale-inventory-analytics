"""Demand model: how much of each SKU customers want on each day.

Per SKU per day, demand is proportional to
    revenue_weight x trend x category_seasonality x show_effect x lifecycle x price_effect
(docs/03_data_spec.md). Demand is realized order-first: each active customer places orders
at a Gamma-distributed rate scaled by the day's aggregate demand index, each order picks
SKUs with probability proportional to the weights above times the customer type's category
affinity, and each line's quantity is a negative binomial number of case packs. Expected
units per SKU-day therefore follow the multiplicative formula, while realized demand is
lumpy, as B2B demand is.

Calibration solves the order-rate scale so expected orders match the scale's target, and
`revenue_weight` divides out each SKU's price and typical line size so expected revenue per
SKU follows the Zipf targets (top 20% of SKUs ~ 77% of revenue).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from generator.config import Config
from generator.randomness import reference_rng
from generator.reference import (
    CATEGORIES,
    CATEGORY_NAMES,
    CUSTOMER_TYPE_NAMES,
    CUSTOMER_TYPES,
    Reference,
)
from generator.timelines import Timelines

WEEKDAY_WEIGHTS = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 0.35, 0.15])  # Mon..Sun
SHOW_LINES_MULTIPLIER = 0.8
SHOW_QTY_MULTIPLIER = 0.6
DUPLICATE_SKU_CORRECTION = 1.15  # empirical; checked by the volume test


@dataclass
class DemandModel:
    weights: np.ndarray  # [day, sku] SKU choice weights before customer-type affinity
    lifecycle: np.ndarray  # [day, sku]
    type_affinity: np.ndarray  # [type, sku]
    show_mask: np.ndarray  # [sku] True for show-relevant categories
    order_index_by_type: np.ndarray  # [type, day] demand index for each customer type x weekday
    show_pos: np.ndarray  # [day] index into ref.shows, or -1
    show_order_rate: np.ndarray  # [day] expected gem-show orders
    rate_scale: float  # converts a customer's raw rate into orders/day
    lines_mean: float  # 1 + mean extra lines per order, before type multipliers
    pack_mean: np.ndarray  # [sku] mean case packs per line
    expected_qty: np.ndarray  # [sku] mean units per line
    gut_rate: np.ndarray  # [sku] the naive buyer's estimate of daily demand
    expected_daily: pd.DataFrame  # truth: expected units per SKU-day over the configured range


def _customer_activity(ref: Reference, days: pd.DatetimeIndex) -> np.ndarray:
    """[day, customer] True when the customer exists, has not churned, and is not a duplicate."""
    c = ref.customers
    created = pd.to_datetime(c["created_date"]).to_numpy()
    churn = pd.to_datetime(c["churn_date"]).to_numpy()
    d = days.to_numpy()[:, None]
    active = created[None, :] <= d
    active &= np.isnat(churn)[None, :] | (d < churn[None, :])
    active &= (c["duplicate_of_pos"].to_numpy() < 0)[None, :]
    return active


def build_demand_model(cfg: Config, ref: Reference, tl: Timelines) -> DemandModel:
    days = tl.days
    t_count = len(days)
    n_range = cfg.scale.n_days
    in_range = np.arange(t_count) < n_range
    p = ref.products
    cat = p["category_pos"].to_numpy()
    start = pd.Timestamp(cfg.scale.start_date)
    day_off = np.arange(t_count)[:, None]

    # Seasonality, trend, lifecycle, price effect: all [day, sku]
    season_table = np.array([cfg.demand["category_seasonality"][c] for c in CATEGORY_NAMES])
    season = season_table[cat][:, days.month - 1].T
    growth = np.array([cfg.demand["category_trend_per_year"][c] for c in CATEGORY_NAMES])[cat]
    trend = (1 + growth)[None, :] ** (day_off / 365.0)

    launch_off = (pd.to_datetime(p["launch_date"]) - start).dt.days.to_numpy()
    disc = pd.to_datetime(p["discontinued_date"])
    disc_off = np.where(disc.isna(), 10**9, (disc - start).dt.days.fillna(0).to_numpy())
    ramp = cfg.demand["launch_ramp_days"]
    decay = cfg.demand["discontinue_decay_days"]
    since_launch = day_off - launch_off[None, :]
    lifecycle = np.where(since_launch < 0, 0.0, np.clip(0.1 + since_launch / ramp, 0.1, 1.0))
    since_disc = day_off - disc_off[None, :]
    lifecycle = np.where(
        since_disc >= 0, lifecycle * np.exp(-np.maximum(since_disc, 0) / decay), lifecycle
    )
    lifecycle = np.where(since_disc > 3 * decay, 0.0, lifecycle)

    price0 = p["list_price_usd"].to_numpy()
    price_effect = (tl.list_price / price0[None, :]) ** (-cfg.demand["price_elasticity"])

    case_pack = p["case_pack_qty"].to_numpy().astype(float)
    units_per_line = np.array([CATEGORIES[c].units_per_line for c in CATEGORY_NAMES])[cat]
    pack_mean = np.maximum(1.0, units_per_line / case_pack)
    expected_qty = case_pack * pack_mean

    revenue_weight = p["revenue_weight"].to_numpy()
    seasonal_base = season * trend * lifecycle
    weights = (revenue_weight / (expected_qty * price0))[None, :] * seasonal_base * price_effect

    # Customer-type affinity per SKU, and show-category mask
    type_affinity = np.array([np.array(CUSTOMER_TYPES[t][4])[cat] for t in CUSTOMER_TYPE_NAMES])
    show_mask = p["is_show_category"].to_numpy()

    # Demand indexes, normalized to 1 over the range. Each customer type orders more often
    # when the categories it buys are in season (landscapers in spring, jewelry makers before
    # the holidays); the aggregate index drives gem-show volume.
    weekday = WEEKDAY_WEIGHTS / WEEKDAY_WEIGHTS.mean()
    agg = (seasonal_base * revenue_weight[None, :]).sum(axis=1)
    agg = agg / agg[in_range].mean()
    order_index = agg * weekday[days.weekday]
    by_type = (seasonal_base * revenue_weight[None, :]) @ type_affinity.T  # [day, type]
    by_type = by_type / by_type[in_range].mean(axis=0, keepdims=True)
    order_index_by_type = (by_type * weekday[days.weekday][:, None]).T  # [type, day]

    # Gem shows active on each day
    show_pos = np.full(t_count, -1)
    show_mult = np.zeros(t_count)
    for s, show in enumerate(ref.shows):
        a = (pd.Timestamp(show.start_date) - start).days
        b = (pd.Timestamp(show.end_date) - start).days
        lo, hi = max(a, 0), min(b, t_count - 1)
        if lo <= hi:
            show_pos[lo : hi + 1] = s
            show_mult[lo : hi + 1] = ref.show_multipliers[s]
    share = cfg.demand["show_category_share"]
    show_extra = np.where(show_pos >= 0, share * (show_mult - 1.0) * agg, 0.0)

    # Calibrate: expected orders over the configured range = target_orders
    activity = _customer_activity(ref, days).astype(float)
    rate_raw = ref.customers["order_rate_raw"].to_numpy()
    ctype_pos = (
        ref.customers["customer_type"]
        .map({t: i for i, t in enumerate(CUSTOMER_TYPE_NAMES)})
        .to_numpy()
    )
    type_onehot = np.eye(len(CUSTOMER_TYPE_NAMES))[ctype_pos]  # [customer, type]
    lam_by_type = activity @ (rate_raw[:, None] * type_onehot)  # [day, type]
    base = cfg.scale.target_orders / (order_index[in_range].sum() + show_extra[in_range].sum())
    unscaled_orders = (lam_by_type * order_index_by_type.T).sum(axis=1)  # [day]
    rate_scale = base * order_index[in_range].sum() / unscaled_orders[in_range].sum()
    show_order_rate = base * show_extra

    # Lines per order: 1 + Poisson(extra x type multiplier). Solve `extra` so the expected mean
    # matches the target, then add a little for lines lost when an order samples the same SKU
    # twice (duplicates are merged into one line).
    lines_mult_by_type = np.array([CUSTOMER_TYPES[t][2] for t in CUSTOMER_TYPE_NAMES])
    orders_by_type = rate_scale * lam_by_type * order_index_by_type.T  # [day, type]
    n_normal = orders_by_type[in_range].sum()
    n_show = show_order_rate[in_range].sum()
    mean_mult = (
        (orders_by_type[in_range] * lines_mult_by_type[None, :]).sum()
        + n_show * SHOW_LINES_MULTIPLIER
    ) / (n_normal + n_show)
    target_mean = cfg.scale.target_order_lines / cfg.scale.target_orders
    lines_mean = 1 + (target_mean - 1) / mean_mult * DUPLICATE_SKU_CORRECTION

    # Expected units per SKU-day (truth), split into normal and gem-show demand
    normal_units = np.zeros((t_count, len(p)))
    for g, tname in enumerate(CUSTOMER_TYPE_NAMES):
        orders_g = orders_by_type[:, g]
        _, qty_mult, lines_mult, _, _ = CUSTOMER_TYPES[tname]
        lines_g = 1 + (lines_mean - 1) * lines_mult
        pg = weights * type_affinity[g][None, :]
        pg = pg / np.maximum(pg.sum(axis=1, keepdims=True), 1e-300)
        normal_units += (orders_g * lines_g)[:, None] * pg * (expected_qty * qty_mult)[None, :]
    ps = weights * show_mask[None, :]
    ps = ps / np.maximum(ps.sum(axis=1, keepdims=True), 1e-300)
    show_lines = 1 + (lines_mean - 1) * SHOW_LINES_MULTIPLIER
    show_units = (show_order_rate * show_lines)[:, None] * ps * (expected_qty * SHOW_QTY_MULTIPLIER)

    # The naive buyer's "gut feel" daily demand: the SKU's typical non-show demand while it's
    # selling, with no seasonality or trend, plus estimation noise.
    selling = (lifecycle >= 0.5) & in_range[:, None]
    mean_selling = (normal_units * selling).sum(axis=0) / np.maximum(selling.sum(axis=0), 1)
    noise_rng = reference_rng(cfg.seed, "setup")
    noise = np.exp(noise_rng.normal(0, cfg.purchasing["gut_feel_noise_sigma"], len(p)))
    gut_rate = mean_selling * noise

    rows = np.flatnonzero(in_range)
    expected_daily = pd.DataFrame(
        {
            "sku": np.tile(p["sku"].to_numpy(), len(rows)),
            "date": np.repeat(days[rows].date, len(p)),
            "expected_units": normal_units[rows].ravel().round(4),
            "expected_show_units": show_units[rows].ravel().round(4),
        }
    )

    return DemandModel(
        weights=weights,
        lifecycle=lifecycle,
        type_affinity=type_affinity,
        show_mask=show_mask,
        order_index_by_type=order_index_by_type,
        show_pos=show_pos,
        show_order_rate=show_order_rate,
        rate_scale=float(rate_scale),
        lines_mean=float(lines_mean),
        pack_mean=pack_mean,
        expected_qty=expected_qty,
        gut_rate=gut_rate,
        expected_daily=expected_daily,
    )
