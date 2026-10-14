"""Day-by-day simulation of the business: orders, fulfillment, purchasing and the stock ledger.

Each simulated day runs in a fixed order, and every inventory movement gets a timestamp that
matches that order, so the ledger summed by timestamp is exactly the simulated stock:

    06:00  purchase order receipts arrive at SD-MAIN
    07:00  customer returns are restocked at SD-MAIN
    07:30  stock transfers to / from gem show booths
    08:00-18:00  sales orders are placed and fulfilled from available stock
                 (quantity_fulfilled < quantity when stock runs out: a stockout)
    19:00  cycle counts at SD-MAIN, with an adjustment movement for every variance
    20:00  the naive buyer places purchase orders

The purchasing policy is deliberately naive (docs/03_data_spec.md): reorder when stock on
hand plus on order falls below a fixed "gut feel" threshold built on the supplier's QUOTED
lead time, and bulk-buy show categories before every gem show with an over-optimism
multiplier. It produces stockouts on fast movers and dead stock on slow ones on purpose.

Stock never goes below zero, because sales, transfers and count adjustments are all capped
by what is on hand.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from generator.config import Config, FxTable
from generator.demand import SHOW_LINES_MULTIPLIER, SHOW_QTY_MULTIPLIER, DemandModel
from generator.randomness import day_rng, stable_uniform
from generator.reference import CUSTOMER_TYPE_NAMES, CUSTOMER_TYPES, MATERIALS, Reference
from generator.timelines import Timelines

WAREHOUSE_IDS = ["SD-MAIN", "SHOW-TUC", "SHOW-DEN"]
WAREHOUSE_POS = {w: i for i, w in enumerate(WAREHOUSE_IDS)}
NORMAL_CHANNELS = ["phone_email", "b2b_portal", "marketplace"]
NORMAL_CHANNEL_P = np.array([0.35, 0.30, 0.15]) / 0.80
SHIP_DELAY_P = np.array([0.30, 0.35, 0.15, 0.10, 0.05, 0.05])  # business days 0..5

LINE_NORMAL, LINE_NEGATIVE_RETURN, LINE_ORPHAN = 0, 1, 2
SEC = np.timedelta64(1, "s")
HOUR = np.timedelta64(3600, "s")
DAY = np.timedelta64(86400, "s")
NAT = np.datetime64("NaT", "s")


@dataclass
class SimResult:
    orders: pd.DataFrame
    lines: pd.DataFrame
    purchase_orders: pd.DataFrame
    po_lines: pd.DataFrame
    movements: pd.DataFrame
    cycle_counts: pd.DataFrame


def _packs_ceil(qty: np.ndarray, pack: np.ndarray) -> np.ndarray:
    return np.ceil(np.maximum(qty, 0) / pack) * pack


class _Collector:
    """Collects per-day arrays and concatenates them into one DataFrame at the end."""

    def __init__(self) -> None:
        self.chunks: list[dict[str, np.ndarray]] = []

    def add(self, **cols) -> None:
        n = len(next(iter(cols.values())))
        if n:
            self.chunks.append({k: np.asarray(v) for k, v in cols.items()})

    def frame(self, columns: list[str]) -> pd.DataFrame:
        if not self.chunks:
            return pd.DataFrame({c: [] for c in columns})
        return pd.DataFrame({c: np.concatenate([ch[c] for ch in self.chunks]) for c in columns})


def run_simulation(cfg: Config, ref: Reference, tl: Timelines, model: DemandModel) -> SimResult:
    days = tl.days
    t_count = len(days)
    start = pd.Timestamp(cfg.scale.start_date)
    fx = FxTable(cfg)

    # --- Products ---
    p = ref.products
    n = len(p)
    skus = p["sku"].to_numpy()
    case_pack = p["case_pack_qty"].to_numpy().astype(float)
    sup_of = p["supplier_pos"].to_numpy()
    is_show_cat = p["is_show_category"].to_numpy()
    launch_off = (pd.to_datetime(p["launch_date"]) - start).dt.days.to_numpy()
    disc = pd.to_datetime(p["discontinued_date"])
    disc_off = np.where(disc.isna(), 10**9, (disc - start).dt.days.fillna(0).to_numpy()).astype(int)
    is_a = p["is_a_class_truth"].to_numpy()

    # --- Suppliers ---
    s = ref.suppliers
    lt_mean = s["true_lead_time_mean_days"].to_numpy()
    lt_sigma = s["true_lead_time_sigma"].to_numpy()
    quoted = s["quoted_lead_time_days"].to_numpy()
    short_prob = s["short_ship_prob"].to_numpy()
    currency = s["currency"].to_numpy()
    supplier_ids = s["supplier_id"].to_numpy()

    # --- Customers ---
    c = ref.customers
    n_cust = len(c)
    type_pos = c["customer_type"].map({t: i for i, t in enumerate(CUSTOMER_TYPE_NAMES)}).to_numpy()
    created_off = (pd.to_datetime(c["created_date"]) - start).dt.days.to_numpy()
    churn = pd.to_datetime(c["churn_date"])
    churn_off = np.where(churn.isna(), 10**9, (churn - start).dt.days.fillna(0).to_numpy())
    is_dup = c["duplicate_of_pos"].to_numpy() >= 0
    rate_raw = c["order_rate_raw"].to_numpy()
    customer_ids = c["customer_id"].to_numpy()
    show_prop = np.array([CUSTOMER_TYPES[t][3] for t in CUSTOMER_TYPE_NAMES])[type_pos]
    qty_mult_type = np.array([CUSTOMER_TYPES[t][1] for t in CUSTOMER_TYPE_NAMES])
    lines_mult_type = np.array([CUSTOMER_TYPES[t][2] for t in CUSTOMER_TYPE_NAMES])
    is_wholesaler = c["customer_type"].to_numpy() == "wholesaler"
    dup_by_orig = {
        int(orig): (dup, int(created_off[dup]))
        for dup, orig in enumerate(c["duplicate_of_pos"].to_numpy())
        if orig >= 0
    }
    cur_rep = c["sales_rep_id"].to_numpy().astype(object).copy()
    cust_events = {d: g for d, g in tl.customer_events.groupby("day_index")}

    # --- Policy parameters ---
    pc = cfg.purchasing
    gut = model.gut_rate
    threshold = gut * quoted[sup_of] * pc["reorder_threshold_buffer"]
    cover_days = pc["order_cover_days"]

    # --- State ---
    on_hand = np.zeros((len(WAREHOUSE_IDS), n))
    flat_on_hand = on_hand.reshape(-1)
    on_order = np.zeros(n)
    arrivals: dict[int, list[dict]] = defaultdict(list)
    po_cancels: dict[int, list[dict]] = defaultdict(list)
    returns: dict[int, list[dict]] = defaultdict(list)
    order_seq: dict[str, int] = defaultdict(int)
    po_seq: dict[str, int] = defaultdict(int)

    # Show transfer and pre-show buying schedules
    transfers_out: dict[int, int] = {}
    transfers_back: dict[int, int] = {}
    prebuys: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for si, show in enumerate(ref.shows):
        a = (pd.Timestamp(show.start_date) - start).days
        b = (pd.Timestamp(show.end_date) - start).days
        if a - pc["show_transfer_lead_days"] >= 0:
            transfers_out[a - pc["show_transfer_lead_days"]] = si
            transfers_back[b + 2] = si
            for j in range(len(s)):
                buy_day = a - int(quoted[j]) - pc["show_prebuy_buffer_days"]
                if buy_day >= 0:
                    prebuys[buy_day].append((si, j))

    count_period = np.where(
        is_a,
        cfg.inventory["cycle_count_period_days_a"],
        cfg.inventory["cycle_count_period_days_other"],
    )
    count_offset = (np.arange(n) * 37) % count_period

    orders_out, lines_out, pos_out, po_lines_out = (
        _Collector(),
        _Collector(),
        _Collector(),
        _Collector(),
    )
    moves_out, counts_out = _Collector(), _Collector()

    # --- Opening balance ---
    opening_skus = np.flatnonzero((launch_off <= 0) & (disc_off > 0))
    opening_qty = _packs_ceil(
        threshold[opening_skus] + gut[opening_skus] * pc["opening_stock_extra_days"],
        case_pack[opening_skus],
    )
    opening_qty = np.maximum(opening_qty, case_pack[opening_skus])
    on_hand[0, opening_skus] = opening_qty

    day_moves: list[dict] = []

    def add_moves(ts, wh, sku, mtype, qty, ref_ids, priority):
        k = len(sku)
        if k:
            day_moves.append(
                {
                    "ts": np.broadcast_to(np.asarray(ts, dtype="datetime64[s]"), (k,)).copy(),
                    "wh": np.broadcast_to(np.asarray(wh), (k,)).copy(),
                    "sku": np.asarray(sku),
                    "type": np.broadcast_to(np.asarray(mtype, dtype=object), (k,)).copy(),
                    "qty": np.asarray(qty, dtype=float),
                    "ref": np.broadcast_to(np.asarray(ref_ids, dtype=object), (k,)).copy(),
                    "prio": np.full(k, priority),
                }
            )

    day0 = days[0].to_datetime64().astype("datetime64[s]")
    add_moves(day0, 0, opening_skus, "adjustment", opening_qty, "OPENING-BALANCE", 0)

    for t in range(t_count):
        day = days[t]
        day64 = day.to_datetime64().astype("datetime64[s]")
        ymd = day.strftime("%Y%m%d")
        ym = day.strftime("%Y%m")

        if t in cust_events:
            for row in cust_events[t].itertuples():
                cur_rep[row.cust_pos] = row.sales_rep_id

        # 06:00 PO receipts and 07:00 returns
        for k, po in enumerate(arrivals.pop(t, [])):
            got = po["received"] > 0
            np.add.at(on_hand[0], po["sku"], po["received"])
            np.subtract.at(on_order, po["sku"], po["ordered"])
            add_moves(day64 + 6 * HOUR + k * 60 * SEC, 0, po["sku"][got], "receipt",
                      po["received"][got], po["line_ids"][got], 1)  # fmt: skip
        for po in po_cancels.pop(t, []):
            np.subtract.at(on_order, po["sku"], po["ordered"])
        for r in returns.pop(t, []):
            np.add.at(on_hand[0], r["sku"], r["qty"])
            add_moves(r["ts"], 0, r["sku"], "return", r["qty"], r["ref"], 2)

        # 07:30 transfers to and from show booths
        if t in transfers_out:
            si = transfers_out[t]
            show = ref.shows[si]
            w = WAREHOUSE_POS[show.warehouse_id]
            send = np.flatnonzero(is_show_cat & (model.lifecycle[t] > 0))
            want = _packs_ceil(
                gut[send] * show.n_days * pc["show_demand_guess_multiplier"], case_pack[send]
            )
            qty = np.minimum(on_hand[0, send], want)
            keep = qty > 0
            send, qty = send[keep], qty[keep]
            on_hand[0, send] -= qty
            on_hand[w, send] += qty
            ref_id = f"TRF-{ymd}-{show.warehouse_id}"
            add_moves(day64 + 7 * HOUR + 30 * 60 * SEC, 0, send, "transfer_out", -qty, ref_id, 3)
            add_moves(day64 + 7 * HOUR + 30 * 60 * SEC, w, send, "transfer_in", qty, ref_id, 3)
        if t in transfers_back:
            show = ref.shows[transfers_back[t]]
            w = WAREHOUSE_POS[show.warehouse_id]
            back = np.flatnonzero(on_hand[w] > 0)
            qty = on_hand[w, back].copy()
            on_hand[w, back] = 0
            on_hand[0, back] += qty
            ref_id = f"TRF-{ymd}-{show.warehouse_id}"
            add_moves(day64 + 7 * HOUR + 30 * 60 * SEC, w, back, "transfer_out", -qty, ref_id, 3)
            add_moves(day64 + 7 * HOUR + 30 * 60 * SEC, 0, back, "transfer_in", qty, ref_id, 3)

        # 08:00-18:00 sales orders
        rng = day_rng(cfg.seed, "demand", t)
        active = (created_off <= t) & (t < churn_off) & ~is_dup
        lam = rate_raw * model.rate_scale * model.order_index[t] * active
        n_per_cust = rng.poisson(lam)
        n_per_cust[active & (created_off == t)] = np.maximum(
            n_per_cust[active & (created_off == t)], 1
        )
        o_cust = np.repeat(np.arange(n_cust), n_per_cust)
        o_show = np.zeros(len(o_cust), dtype=bool)
        o_wh = np.zeros(len(o_cust), dtype=int)
        si = model.show_pos[t]
        if si >= 0 and active.any():
            n_show = rng.poisson(model.show_order_rate[t])
            prop = show_prop * active
            show_cust = rng.choice(n_cust, n_show, p=prop / prop.sum())
            o_cust = np.concatenate([o_cust, show_cust])
            o_show = np.concatenate([o_show, np.ones(n_show, dtype=bool)])
            o_wh = np.concatenate(
                [o_wh, np.full(n_show, WAREHOUSE_POS[ref.shows[si].warehouse_id])]
            )
        n_orders = len(o_cust)
        if n_orders:
            seconds = np.where(
                o_show,
                rng.integers(9 * 3600, 18 * 3600, n_orders),
                rng.integers(8 * 3600, 18 * 3600, n_orders),
            )
            order = np.argsort(seconds, kind="stable")
            o_cust, o_show, o_wh, seconds = (
                o_cust[order],
                o_show[order],
                o_wh[order],
                seconds[order],
            )
            o_type = type_pos[o_cust]
            channel = np.where(
                o_show, "gem_show", rng.choice(NORMAL_CHANNELS, n_orders, p=NORMAL_CHANNEL_P)
            )
            order_ids = []
            for _ in range(n_orders):
                order_seq[ym] += 1
                order_ids.append(f"SO-{ym}-{order_seq[ym]:05d}")
            order_ids = np.array(order_ids, dtype=object)
            placed_ts = day64 + seconds * SEC

            # Lines: sample SKUs by the day's weights x customer-type affinity
            lines_mult = np.where(o_show, SHOW_LINES_MULTIPLIER, lines_mult_type[o_type])
            n_lines = 1 + rng.poisson((model.lines_mean - 1) * lines_mult)
            l_order = np.repeat(np.arange(n_orders), n_lines)
            l_group = np.where(o_show, -1, o_type)[l_order]
            l_sku = np.empty(len(l_order), dtype=int)
            for g in np.unique(l_group):
                mask = l_group == g
                if g == -1:
                    w_g = model.weights[t] * model.show_mask
                else:
                    w_g = model.weights[t] * model.type_affinity[g]
                l_sku[mask] = rng.choice(n, mask.sum(), p=w_g / w_g.sum())
            key = np.unique(l_order * n + l_sku)
            l_order, l_sku = key // n, key % n
            first = np.searchsorted(l_order, np.arange(n_orders))
            line_no = np.arange(len(l_order)) - first[l_order] + 1
            n_lines = np.bincount(l_order, minlength=n_orders)

            # Quantities: negative binomial number of case packs, sometimes off-pack
            r = cfg.demand["qty_dispersion"]
            pm = model.pack_mean[l_sku]
            packs = 1 + rng.negative_binomial(r, r / (r + pm - 1))
            qmult = np.where(o_show[l_order], SHOW_QTY_MULTIPLIER, qty_mult_type[o_type[l_order]])
            qty = case_pack[l_sku] * np.maximum(1, np.round(packs * qmult))
            loose = rng.random(len(qty)) < 0.10
            qty = np.where(
                loose, np.maximum(1, np.round(qty * rng.uniform(0.5, 1.5, len(qty)))), qty
            )

            # Fulfillment in order-placement sequence, capped by stock at the order's warehouse
            cancelled = rng.random(n_orders) < cfg.orders["cancel_rate"]
            need = np.where(cancelled[l_order], 0.0, qty)
            lkey = o_wh[l_order] * n + l_sku
            srt = np.argsort(lkey, kind="stable")
            k_sorted, need_sorted = lkey[srt], need[srt]
            seg_start = np.r_[0, np.flatnonzero(np.diff(k_sorted)) + 1]
            seg_id = np.repeat(np.arange(len(seg_start)), np.diff(np.r_[seg_start, len(k_sorted)]))
            cum_before = np.cumsum(need_sorted) - need_sorted
            before = cum_before - cum_before[seg_start][seg_id]
            filled_sorted = np.clip(flat_on_hand[k_sorted] - before, 0, need_sorted)
            filled = np.empty_like(filled_sorted)
            filled[srt] = filled_sorted
            np.subtract.at(flat_on_hand, lkey, filled)

            order_filled = np.bincount(l_order, weights=filled, minlength=n_orders)
            stockout_cancel = ~cancelled & (order_filled == 0)

            # Prices and discounts
            list_price = tl.list_price[t, l_sku]
            negotiated = rng.random(len(l_sku)) < cfg.orders["negotiated_price_share"]
            unit_price = np.where(
                negotiated,
                np.round(list_price * (1 - rng.uniform(0.03, 0.12, len(l_sku))), 2),
                list_price,
            )
            line_disc = np.where(
                rng.random(len(l_sku)) < cfg.orders["line_discount_share"],
                rng.choice([5.0, 10.0], len(l_sku)),
                0.0,
            )
            discounted = is_wholesaler[o_cust] | (o_show & (rng.random(n_orders) < 0.5))
            order_disc = np.where(discounted, rng.integers(5, 16, n_orders).astype(float), 0.0)

            # Status timeline: placed -> shipped -> delivered (-> returned), or cancelled
            cancel_ts = np.full(n_orders, NAT)
            cancel_ts[cancelled] = (
                placed_ts[cancelled] + rng.integers(3600, 48 * 3600, cancelled.sum()) * SEC
            )
            cancel_ts[stockout_cancel] = placed_ts[stockout_cancel] + HOUR
            is_cancelled = cancelled | stockout_cancel
            ship_delay = rng.choice(6, n_orders, p=SHIP_DELAY_P)
            ship_day = np.busday_offset(
                np.full(n_orders, np.datetime64(day.date(), "D")), ship_delay, roll="forward"
            )
            ship_ts = (
                ship_day.astype("datetime64[s]") + 15 * HOUR + rng.integers(0, 7200, n_orders) * SEC
            )
            deliver_ts = (
                ship_day.astype("datetime64[s]") + rng.integers(2, 8, n_orders) * DAY + 12 * HOUR
            )
            ship_ts = np.where(o_show, placed_ts + 600 * SEC, ship_ts)
            deliver_ts = np.where(o_show, placed_ts + 1200 * SEC, deliver_ts)
            ship_ts[is_cancelled] = NAT
            deliver_ts[is_cancelled] = NAT

            returned = ~is_cancelled & (rng.random(n_orders) < cfg.orders["return_rate"])
            return_day_off = rng.integers(5, 31, n_orders)
            return_ts = np.full(n_orders, NAT)
            ret_secs = rng.integers(0, 1800, n_orders)
            deliver_day = deliver_ts.astype("datetime64[D]").astype("datetime64[s]")
            return_ts[returned] = (
                deliver_day[returned]
                + return_day_off[returned] * DAY
                + 7 * HOUR
                + ret_secs[returned] * SEC
            )

            line_ids = np.array(
                [f"{order_ids[o]}-{ln:02d}" for o, ln in zip(l_order, line_no, strict=True)],
                dtype=object,
            )

            # Whole-order returns: restock every fulfilled line at SD-MAIN on the return date
            for o in np.flatnonzero(returned):
                sel = (l_order == o) & (filled > 0)
                if sel.any():
                    rday = t + int((return_ts[o] - day64) // DAY)
                    returns[rday].append(
                        {
                            "sku": l_sku[sel],
                            "qty": filled[sel],
                            "ref": line_ids[sel],
                            "ts": return_ts[o],
                        }
                    )

            # Planted issue 6: partial returns keyed as an extra negative-quantity line
            neg = (
                (filled > 0)
                & ~returned[l_order]
                & (rng.random(len(l_sku)) < cfg.planted_issues["negative_quantity_returns"])
            )
            neg_qty = np.maximum(1, np.round(filled * rng.uniform(0.1, 0.5, len(filled))))
            neg_days = rng.integers(3, 31, len(filled))
            neg_secs = rng.integers(1800, 3600, len(filled))
            last_line_return_ts = np.full(n_orders, NAT)

            # Planted issue 9: lines keyed with a SKU code that doesn't exist (never fulfilled)
            orphan = (
                rng.random(n_orders) < cfg.planted_issues["orphan_order_lines"] * model.lines_mean
            )
            mat_codes = [v[0] for v in MATERIALS.values()]
            orphan_codes = [
                f"{mat_codes[int(a)]}-{b}-{9000 + int(x):04d}"
                for a, b, x in zip(
                    rng.integers(0, len(mat_codes), n_orders),
                    rng.choice(["PLS", "TMB", "JWL", "CLU"], n_orders),
                    rng.integers(0, 1000, n_orders),
                    strict=True,
                )
            ]
            orphan_qty = rng.integers(1, 13, n_orders).astype(float)
            orphan_price = np.round(rng.uniform(5, 60, n_orders), 2)

            extra_lines = []
            for o in np.flatnonzero(orphan):
                extra_lines.append(
                    (f"{order_ids[o]}-{n_lines[o] + 1:02d}", order_ids[o], n_lines[o] + 1, -1,
                     orphan_codes[o], orphan_qty[o], 0.0, orphan_price[o], 0.0, day64, LINE_ORPHAN)
                )  # fmt: skip
            next_line = n_lines + 1 + orphan.astype(int)
            for li in np.flatnonzero(neg):
                o = l_order[li]
                ret_ts = deliver_day[o] + neg_days[li] * DAY + 7 * HOUR + neg_secs[li] * SEC
                lid = f"{order_ids[o]}-{next_line[o]:02d}"
                extra_lines.append(
                    (lid, order_ids[o], next_line[o], l_sku[li], "", -neg_qty[li], -neg_qty[li],
                     unit_price[li], line_disc[li], ret_ts.astype("datetime64[D]").astype("datetime64[s]"),
                     LINE_NEGATIVE_RETURN)
                )  # fmt: skip
                next_line[o] += 1
                last_line_return_ts[o] = (
                    max(last_line_return_ts[o], ret_ts)
                    if not np.isnat(last_line_return_ts[o])
                    else ret_ts
                )
                rday = t + int((ret_ts - day64) // DAY)
                returns[rday].append(
                    {"sku": np.array([l_sku[li]]), "qty": np.array([neg_qty[li]]),
                     "ref": np.array([lid], dtype=object), "ts": ret_ts}
                )  # fmt: skip

            # Planted issue 1: some orders from customers with a duplicate record use the duplicate ID
            reported = o_cust.copy()
            for o in range(n_orders):
                dup = dup_by_orig.get(int(o_cust[o]))
                if (
                    dup
                    and t >= dup[1]
                    and stable_uniform(cfg.seed, f"dup_order|{order_ids[o]}") < 0.5
                ):
                    reported[o] = dup[0]

            orders_out.add(
                order_id=order_ids,
                cust_pos=o_cust,
                customer_id=customer_ids[reported],
                order_date=np.full(n_orders, day64),
                placed_ts=placed_ts,
                channel=channel,
                warehouse_id=np.array(WAREHOUSE_IDS, dtype=object)[o_wh],
                order_discount_pct=order_disc,
                sales_rep_id=cur_rep[o_cust],
                cancel_ts=cancel_ts,
                ship_ts=ship_ts,
                deliver_ts=deliver_ts,
                return_ts=return_ts,
                line_return_ts=last_line_return_ts,
            )
            lines_out.add(
                order_line_id=line_ids,
                order_id=order_ids[l_order],
                line_no=line_no,
                sku_pos=l_sku,
                sku_text=np.full(len(l_sku), "", dtype=object),
                quantity=qty,
                quantity_fulfilled=filled,
                unit_price_usd=unit_price,
                line_discount_pct=line_disc,
                emit_date=np.full(len(l_sku), day64),
                line_kind=np.full(len(l_sku), LINE_NORMAL),
            )
            if extra_lines:
                cols = list(zip(*extra_lines, strict=True))
                lines_out.add(
                    order_line_id=np.array(cols[0], dtype=object),
                    order_id=np.array(cols[1], dtype=object),
                    line_no=np.array(cols[2]),
                    sku_pos=np.array(cols[3]),
                    sku_text=np.array(cols[4], dtype=object),
                    quantity=np.array(cols[5], dtype=float),
                    quantity_fulfilled=np.array(cols[6], dtype=float),
                    unit_price_usd=np.array(cols[7], dtype=float),
                    line_discount_pct=np.array(cols[8], dtype=float),
                    emit_date=np.array(cols[9], dtype="datetime64[s]"),
                    line_kind=np.array(cols[10]),
                )

            sold = filled > 0
            add_moves(placed_ts[l_order][sold], o_wh[l_order][sold], l_sku[sold], "sale",
                      -filled[sold], line_ids[sold], 4)  # fmt: skip

        # 19:00 cycle counts at SD-MAIN
        due = np.flatnonzero((launch_off <= t) & ((t - count_offset) % count_period == 0))
        if len(due):
            crng = day_rng(cfg.seed, "counts", t)
            system = on_hand[0, due].copy()
            lo, hi = cfg.inventory["count_noise_range"]
            counted = system + np.round(system * crng.uniform(lo, hi, len(due)))
            big_miss = (crng.random(len(due)) < cfg.inventory["big_miss_rate"]) & (system >= 10)
            counted = np.where(
                big_miss, np.floor(system * crng.uniform(0.3, 0.8, len(due))), counted
            )
            counted = np.maximum(counted, 0)
            count_ids = np.array([f"CC-{ymd}-{k + 1:04d}" for k in range(len(due))], dtype=object)
            count_ts = day64 + 19 * HOUR + np.arange(len(due)) * SEC
            counts_out.add(
                count_id=count_ids,
                count_date=np.full(len(due), day64),
                warehouse_id=np.full(len(due), "SD-MAIN", dtype=object),
                sku_pos=due,
                system_qty=system,
                counted_qty=counted,
                is_big_miss=big_miss,
            )
            var = counted != system
            on_hand[0, due[var]] = counted[var]
            add_moves(
                count_ts[var] + SEC,
                0,
                due[var],
                "adjustment",
                (counted - system)[var],
                count_ids[var],
                5,
            )

        # 20:00 naive purchasing
        prng = day_rng(cfg.seed, "purchasing", t)
        orderable = (launch_off - quoted[sup_of] <= t) & (t < disc_off)
        new_pos: list[tuple[int, np.ndarray, np.ndarray, str]] = []
        for si, j in prebuys.get(t, []):
            sel = np.flatnonzero((sup_of == j) & is_show_cat & orderable)
            if len(sel):
                show = ref.shows[si]
                lo, hi = pc["show_overbuy_multiplier_range"]
                want = (
                    gut[sel]
                    * show.n_days
                    * pc["show_demand_guess_multiplier"]
                    * prng.uniform(lo, hi, len(sel))
                )
                qty = np.maximum(
                    _packs_ceil(want, case_pack[sel]),
                    pc["show_prebuy_min_case_packs"] * case_pack[sel],
                )
                new_pos.append((j, sel, qty, "show_prebuy"))
        position = on_hand[0] + on_order
        trigger = np.flatnonzero(orderable & (position <= threshold))
        for j in np.unique(sup_of[trigger]):
            sel = trigger[sup_of[trigger] == j]
            qty = np.maximum(_packs_ceil(gut[sel] * cover_days, case_pack[sel]), case_pack[sel])
            new_pos.append((int(j), sel, qty, "regular"))

        for k, (j, sel, qty, kind) in enumerate(new_pos):
            po_seq[ym] += 1
            po_id = f"PO-{ym}-{po_seq[ym]:04d}"
            created_ts = day64 + 20 * HOUR + k * 60 * SEC
            lt = lt_mean[j] * np.exp(lt_sigma[j] * prng.normal() - lt_sigma[j] ** 2 / 2)
            arrive = t + max(1, round(lt))
            transit = t + max(1, round(lt * prng.uniform(0.1, 0.4)))
            cancelled = prng.random() < pc["po_cancel_rate"]
            cancel_off = t + int(prng.integers(1, 11))
            short = prng.random(len(sel)) < short_prob[j]
            received = np.where(short, np.floor(qty * prng.uniform(0.6, 0.95, len(sel))), qty)
            rate = fx.rate(day.date(), currency[j])
            unit_cost_local = np.round(tl.unit_cost[t, sel] * rate, 2)
            line_ids = np.array([f"{po_id}-{m + 1:02d}" for m in range(len(sel))], dtype=object)
            on_order[sel] += qty

            arrival_ts = (
                NAT
                if cancelled
                else days[0].to_datetime64().astype("datetime64[s]") + arrive * DAY + 6 * HOUR
            )
            transit_ts = (
                NAT if cancelled or transit >= arrive else day64 + (transit - t) * DAY + 10 * HOUR
            )
            cancel_ts = day64 + (cancel_off - t) * DAY + 10 * HOUR if cancelled else NAT
            if cancelled:
                po_cancels[cancel_off].append({"sku": sel, "ordered": qty})
            else:
                arrivals[arrive].append(
                    {"sku": sel, "ordered": qty, "received": received, "line_ids": line_ids}
                )
            pos_out.add(
                po_id=np.array([po_id], dtype=object),
                supplier_id=np.array([supplier_ids[j]], dtype=object),
                order_date=np.array([day64]),
                created_ts=np.array([created_ts]),
                expected_arrival=np.array([day64 + int(quoted[j]) * DAY]),
                transit_ts=np.array([transit_ts], dtype="datetime64[s]"),
                arrival_ts=np.array([arrival_ts], dtype="datetime64[s]"),
                cancel_ts=np.array([cancel_ts], dtype="datetime64[s]"),
                is_short=np.array([bool(short.any())]),
                currency=np.array([currency[j]], dtype=object),
                po_kind=np.array([kind], dtype=object),
            )
            po_lines_out.add(
                po_line_id=line_ids,
                po_id=np.full(len(sel), po_id, dtype=object),
                sku_pos=sel,
                quantity_ordered=qty.astype(float),
                quantity_received=received.astype(float),
                unit_cost_local=unit_cost_local,
                arrival_ts=np.full(len(sel), arrival_ts, dtype="datetime64[s]"),
            )

        # Finish the day's ledger: order movements by (timestamp, processing priority)
        if day_moves:
            m = {k: np.concatenate([d[k] for d in day_moves]) for k in day_moves[0]}
            o = np.lexsort((np.arange(len(m["ts"])), m["prio"], m["ts"]))
            n_m = len(o)
            moves_out.add(
                movement_id=np.array([f"MV-{ymd}-{i + 1:06d}" for i in range(n_m)], dtype=object),
                movement_ts=m["ts"][o],
                warehouse_id=np.array(WAREHOUSE_IDS, dtype=object)[m["wh"][o].astype(int)],
                sku_pos=m["sku"][o].astype(int),
                movement_type=m["type"][o],
                quantity=m["qty"][o],
                reference_id=m["ref"][o],
            )
            day_moves = []

    orders = orders_out.frame(
        ["order_id", "cust_pos", "customer_id", "order_date", "placed_ts", "channel", "warehouse_id",
         "order_discount_pct", "sales_rep_id", "cancel_ts", "ship_ts", "deliver_ts", "return_ts",
         "line_return_ts"]
    )  # fmt: skip
    lines = lines_out.frame(
        ["order_line_id", "order_id", "line_no", "sku_pos", "sku_text", "quantity",
         "quantity_fulfilled", "unit_price_usd", "line_discount_pct", "emit_date", "line_kind"]
    )  # fmt: skip
    lines["sku"] = np.where(
        lines["sku_pos"] >= 0, skus[lines["sku_pos"].clip(lower=0)], lines["sku_text"]
    )
    purchase_orders = pos_out.frame(
        ["po_id", "supplier_id", "order_date", "created_ts", "expected_arrival", "transit_ts",
         "arrival_ts", "cancel_ts", "is_short", "currency", "po_kind"]
    )  # fmt: skip
    po_lines = po_lines_out.frame(
        ["po_line_id", "po_id", "sku_pos", "quantity_ordered", "quantity_received",
         "unit_cost_local", "arrival_ts"]
    )  # fmt: skip
    po_lines["sku"] = skus[po_lines["sku_pos"].astype(int)]
    movements = moves_out.frame(
        ["movement_id", "movement_ts", "warehouse_id", "sku_pos", "movement_type", "quantity",
         "reference_id"]
    )  # fmt: skip
    movements["sku"] = skus[movements["sku_pos"].astype(int)]
    cycle_counts = counts_out.frame(
        ["count_id", "count_date", "warehouse_id", "sku_pos", "system_qty", "counted_qty", "is_big_miss"]
    )  # fmt: skip
    cycle_counts["sku"] = skus[cycle_counts["sku_pos"].astype(int)]
    return SimResult(orders, lines, purchase_orders, po_lines, movements, cycle_counts)
