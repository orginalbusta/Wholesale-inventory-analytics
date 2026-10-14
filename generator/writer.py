"""Turn the simulation into ERP-style extracts and write them as parquet.

Two kinds of run:
    backfill      every table as of the end date, run_id = "backfill"
    simulate-day  only rows created or changed on one day, run_id = "<YYYY-MM-DD>"
                  (new orders, status changes to older orders, receipts, price changes, ...)

Mutable tables (orders, purchase orders, products, customers) are written as the version in
effect at the end of the extraction day, with `updated_at` = time of the last change. Every
row gets `_extracted_at` = 02:00 the morning after the extraction day: a simulated timestamp,
so output is reproducible.

Output layout: data/raw/erp/<table>/<run_id>.parquet, data/_truth/...
"""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from generator.config import Config
from generator.demand import DemandModel
from generator.issues import apply_issues
from generator.reference import Reference
from generator.simulate import SimResult
from generator.timelines import Timelines

STR, FLOAT, INT, BOOL = pa.string(), pa.float64(), pa.int64(), pa.bool_()
DATE, TS = pa.date32(), pa.timestamp("us")

SCHEMAS: dict[str, list[tuple[str, pa.DataType]]] = {
    "warehouses": [("warehouse_id", STR), ("warehouse_name", STR), ("warehouse_type", STR),
                   ("city", STR), ("state", STR), ("is_seasonal", BOOL)],
    "suppliers": [("supplier_id", STR), ("supplier_name", STR), ("country", STR), ("currency", STR),
                  ("payment_terms", STR), ("min_order_value_usd", FLOAT), ("created_at", DATE)],
    "products": [("sku", STR), ("product_name", STR), ("category", STR), ("material", STR),
                 ("primary_supplier_id", STR), ("unit_of_measure", STR), ("unit_cost_usd", FLOAT),
                 ("list_price_usd", FLOAT), ("case_pack_qty", INT), ("launch_date", DATE),
                 ("discontinued_date", DATE), ("is_active", BOOL), ("updated_at", TS)],
    "product_price_history": [("price_change_id", STR), ("sku", STR), ("effective_date", DATE),
                              ("unit_cost_usd", FLOAT), ("list_price_usd", FLOAT), ("changed_at", TS)],
    "customers": [("customer_id", STR), ("customer_name", STR), ("customer_type", STR),
                  ("contact_email", STR), ("state", STR), ("credit_terms", STR), ("sales_rep_id", STR),
                  ("first_order_date", DATE), ("created_at", TS), ("updated_at", TS)],
    "sales_orders": [("order_id", STR), ("customer_id", STR), ("order_date", DATE), ("channel", STR),
                     ("warehouse_id", STR), ("status", STR), ("ship_date", DATE),
                     ("order_discount_pct", FLOAT), ("sales_rep_id", STR), ("updated_at", TS)],
    "sales_order_lines": [("order_line_id", STR), ("order_id", STR), ("line_no", INT), ("sku", STR),
                          ("quantity", FLOAT), ("quantity_fulfilled", FLOAT), ("unit_price_usd", FLOAT),
                          ("line_discount_pct", FLOAT)],
    "purchase_orders": [("po_id", STR), ("supplier_id", STR), ("order_date", DATE),
                        ("expected_arrival_date", STR), ("actual_arrival_date", DATE), ("status", STR),
                        ("currency", STR), ("updated_at", TS)],
    "purchase_order_lines": [("po_line_id", STR), ("po_id", STR), ("sku", STR),
                             ("quantity_ordered", FLOAT), ("quantity_received", FLOAT),
                             ("unit_cost_local", FLOAT)],
    "inventory_movements": [("movement_id", STR), ("movement_ts", TS), ("warehouse_id", STR),
                            ("sku", STR), ("movement_type", STR), ("quantity", FLOAT),
                            ("reference_id", STR)],
    "cycle_counts": [("count_id", STR), ("count_date", DATE), ("warehouse_id", STR), ("sku", STR),
                     ("system_qty", FLOAT), ("counted_qty", FLOAT)],
}  # fmt: skip
TABLES = list(SCHEMAS)


# --- Arrow conversion ----------------------------------------------------------------------


def _arrow_column(values, dtype: pa.DataType) -> pa.Array:
    if dtype == TS:
        return pa.array(np.asarray(values, dtype="datetime64[us]"), type=TS, from_pandas=True)
    if dtype == DATE:
        return pa.array(np.asarray(values, dtype="datetime64[D]"), type=DATE, from_pandas=True)
    if dtype == STR:
        return pa.array(
            [
                None if (v is None or (isinstance(v, float) and np.isnan(v))) else str(v)
                for v in values
            ],
            type=STR,
        )
    return pa.array(np.asarray(values), type=dtype, from_pandas=True)


def to_arrow(df: pd.DataFrame, table: str, extracted_at: np.datetime64) -> pa.Table:
    cols = SCHEMAS[table] + [("_extracted_at", TS)]
    df = df.assign(_extracted_at=extracted_at)
    arrays = [
        _arrow_column(df[name].to_numpy(dtype=object if t == STR else None), t) for name, t in cols
    ]
    return pa.Table.from_arrays(arrays, schema=pa.schema(cols))


def write_parquet(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="snappy")


# --- As-of table builders -----------------------------------------------------------------


def _latest(*cols: np.ndarray, cutoff: np.datetime64) -> np.ndarray:
    """Row-wise max of the timestamps that happened before `cutoff` (NaT if none)."""
    stacked = np.stack([np.where(c < cutoff, c, np.datetime64("NaT", "s")) for c in cols])
    out = np.full(stacked.shape[1], np.datetime64("NaT", "s"))
    for row in stacked:
        better = ~np.isnat(row) & (np.isnat(out) | (row > out))
        out[better] = row[better]
    return out


def build_tables(
    cfg: Config,
    ref: Reference,
    tl: Timelines,
    sim: SimResult,
    as_of: date,
    day_only: bool,
) -> dict[str, pd.DataFrame]:
    cutoff = np.datetime64(as_of + timedelta(days=1), "s")
    window_start = np.datetime64(as_of, "s") if day_only else np.datetime64("1900-01-01", "s")
    t_as_of = (as_of - cfg.scale.start_date).days

    def in_window(ts: np.ndarray) -> np.ndarray:
        return (ts >= window_start) & (ts < cutoff)

    out: dict[str, pd.DataFrame] = {}

    # Warehouses and suppliers are static: written once, by the backfill
    out["warehouses"] = ref.warehouses if not day_only else ref.warehouses.iloc[0:0]
    out["suppliers"] = ref.suppliers if not day_only else ref.suppliers.iloc[0:0]

    # Products, as of the end of the day
    p = ref.products
    disc = pd.to_datetime(p["discontinued_date"]).to_numpy().astype("datetime64[s]")
    disc_known = disc < cutoff
    pe = tl.price_events[tl.price_events["day_index"] <= t_as_of]
    last_price_change = pe.groupby("sku_pos")["changed_at"].max()
    last_change = np.full(len(p), np.datetime64("NaT", "s"))
    last_change[last_price_change.index.to_numpy()] = last_price_change.to_numpy().astype(
        "datetime64[s]"
    )
    updated = _latest(
        ref.product_created_ts, last_change, disc + 9 * np.timedelta64(3600, "s"), cutoff=cutoff
    )
    products = pd.DataFrame(
        {
            "sku": p["sku"],
            "product_name": p["product_name"],
            "category": p["category"],
            "material": p["material"],
            "primary_supplier_id": p["primary_supplier_id"],
            "unit_of_measure": p["unit_of_measure"],
            "unit_cost_usd": tl.unit_cost[t_as_of],
            "list_price_usd": tl.list_price[t_as_of],
            "case_pack_qty": p["case_pack_qty"],
            "launch_date": p["launch_date"],
            "discontinued_date": np.where(disc_known, disc, np.datetime64("NaT", "s")),
            "is_active": ~disc_known,
            "updated_at": updated,
        }
    )
    keep = (ref.product_created_ts < cutoff) & (in_window(updated) if day_only else True)
    out["products"] = products[keep].reset_index(drop=True)

    # Product price history (initial state + every cost/price change)
    initial = pd.DataFrame(
        {
            "sku_pos": np.arange(len(p)),
            "changed_at": ref.product_created_ts,
            "unit_cost_usd": p["unit_cost_usd"],
            "list_price_usd": p["list_price_usd"],
        }
    )
    hist = pd.concat([initial, tl.price_events.drop(columns="day_index")], ignore_index=True)
    hist["changed_at"] = hist["changed_at"].to_numpy().astype("datetime64[s]")
    hist = hist.sort_values(["changed_at", "sku_pos"], kind="stable").reset_index(drop=True)
    hist["price_change_id"] = [f"PCH-{i + 1:07d}" for i in range(len(hist))]
    hist["sku"] = p["sku"].to_numpy()[hist["sku_pos"]]
    hist["effective_date"] = hist["changed_at"].to_numpy().astype("datetime64[D]")
    out["product_price_history"] = hist[in_window(hist["changed_at"].to_numpy())].reset_index(
        drop=True
    )

    # Customers, as of the end of the day
    c = ref.customers
    created_ts = pd.to_datetime(c["created_date"]).to_numpy().astype(
        "datetime64[s]"
    ) + np.timedelta64(7 * 3600, "s")
    ce = tl.customer_events[tl.customer_events["day_index"] <= t_as_of]
    last_ce = ce.groupby("cust_pos").tail(1).set_index("cust_pos")
    terms = c["credit_terms"].to_numpy().astype(object).copy()
    reps = c["sales_rep_id"].to_numpy().astype(object).copy()
    last_cust_change = np.full(len(c), np.datetime64("NaT", "s"))
    if len(last_ce):
        idx = last_ce.index.to_numpy()
        terms[idx] = last_ce["credit_terms"].to_numpy()
        reps[idx] = last_ce["sales_rep_id"].to_numpy()
        last_cust_change[idx] = last_ce["changed_at"].to_numpy().astype("datetime64[s]")
    cust_updated = _latest(created_ts, last_cust_change, cutoff=cutoff)
    dup_pos = c["duplicate_of_pos"].to_numpy()
    customers = pd.DataFrame(
        {
            "customer_id": c["customer_id"],
            "customer_name": c["customer_name"],
            "customer_type": c["customer_type"],
            "contact_email": c["contact_email"],
            "state": c["state"],
            "credit_terms": terms,
            "sales_rep_id": reps,
            "first_order_date": c["first_order_date"],
            "created_at": created_ts,
            "updated_at": cust_updated,
            "_duplicate_of_id": np.where(
                dup_pos >= 0, c["customer_id"].to_numpy()[np.maximum(dup_pos, 0)], None
            ),
        }
    )
    keep = created_ts < cutoff
    if day_only:
        keep &= in_window(cust_updated)
    out["customers"] = customers[keep].reset_index(drop=True)

    # Sales orders: status and updated_at as of the end of the day
    o = sim.orders
    ts = {k: o[k].to_numpy().astype("datetime64[s]") for k in
          ["placed_ts", "cancel_ts", "ship_ts", "deliver_ts", "return_ts", "line_return_ts"]}  # fmt: skip
    status = np.full(len(o), "placed", dtype=object)
    status[ts["ship_ts"] < cutoff] = "shipped"
    status[ts["deliver_ts"] < cutoff] = "delivered"
    status[ts["return_ts"] < cutoff] = "returned"
    status[ts["cancel_ts"] < cutoff] = "cancelled"
    o_updated = _latest(*ts.values(), cutoff=cutoff)
    orders = pd.DataFrame(
        {
            "order_id": o["order_id"],
            "customer_id": o["customer_id"],
            "order_date": o["order_date"].to_numpy().astype("datetime64[D]"),
            "channel": o["channel"],
            "warehouse_id": o["warehouse_id"],
            "status": status,
            "ship_date": np.where(
                ts["ship_ts"] < cutoff,
                ts["ship_ts"].astype("datetime64[D]"),
                np.datetime64("NaT", "D"),
            ),
            "order_discount_pct": o["order_discount_pct"],
            "sales_rep_id": o["sales_rep_id"],
            "updated_at": o_updated,
            "_canonical_customer_id": c["customer_id"].to_numpy()[
                o["cust_pos"].to_numpy().astype(int)
            ],
            "_placed_ts": ts["placed_ts"],
            "_run_date": np.datetime64(as_of, "D"),
        }
    )
    keep = ts["placed_ts"] < cutoff
    if day_only:
        keep &= in_window(o_updated)
    out["sales_orders"] = orders[keep].reset_index(drop=True)

    # Sales order lines: written when created (negative return lines appear on the return date)
    ln = sim.lines
    emit = ln["emit_date"].to_numpy().astype("datetime64[s]")
    lines = ln[in_window(emit)].reset_index(drop=True)
    out["sales_order_lines"] = lines.rename(columns={"line_kind": "_line_kind"})

    # Purchase orders and lines
    po = sim.purchase_orders
    pts = {
        k: po[k].to_numpy().astype("datetime64[s]")
        for k in ["created_ts", "transit_ts", "arrival_ts", "cancel_ts"]
    }
    arrived = pts["arrival_ts"] < cutoff
    po_status = np.full(len(po), "open", dtype=object)
    po_status[pts["transit_ts"] < cutoff] = "in_transit"
    po_status[arrived] = np.where(
        po["is_short"].to_numpy()[arrived], "partially_received", "received"
    )
    po_status[pts["cancel_ts"] < cutoff] = "cancelled"
    po_updated = _latest(*pts.values(), cutoff=cutoff)
    purchase_orders = pd.DataFrame(
        {
            "po_id": po["po_id"],
            "supplier_id": po["supplier_id"],
            "order_date": po["order_date"].to_numpy().astype("datetime64[D]"),
            "expected_arrival_date": po["expected_arrival"].to_numpy().astype("datetime64[D]"),
            "actual_arrival_date": np.where(
                arrived, pts["arrival_ts"].astype("datetime64[D]"), np.datetime64("NaT", "D")
            ),
            "status": po_status,
            "currency": po["currency"],
            "updated_at": po_updated,
        }
    )
    keep_po = pts["created_ts"] < cutoff
    if day_only:
        keep_po &= in_window(po_updated)
    out["purchase_orders"] = purchase_orders[keep_po].reset_index(drop=True)

    pl = sim.po_lines
    line_arrived = pl["arrival_ts"].to_numpy().astype("datetime64[s]") < cutoff
    po_lines = pd.DataFrame(
        {
            "po_line_id": pl["po_line_id"],
            "po_id": pl["po_id"],
            "sku": pl["sku"],
            "quantity_ordered": pl["quantity_ordered"],
            "quantity_received": np.where(line_arrived, pl["quantity_received"], np.nan),
            "unit_cost_local": pl["unit_cost_local"],
        }
    )
    created_by_po = dict(zip(po["po_id"], pts["created_ts"], strict=True))
    line_created = pl["po_id"].map(created_by_po).to_numpy().astype("datetime64[s]")
    keep_pl = line_created < cutoff
    if day_only:
        keep_pl &= in_window(line_created) | in_window(
            pl["arrival_ts"].to_numpy().astype("datetime64[s]")
        )
    out["purchase_order_lines"] = po_lines[keep_pl].reset_index(drop=True)

    # Ledger tables: append-only
    mv = sim.movements
    out["inventory_movements"] = mv[
        in_window(mv["movement_ts"].to_numpy().astype("datetime64[s]"))
    ].reset_index(drop=True)
    cc = sim.cycle_counts
    counts = cc[in_window(cc["count_date"].to_numpy().astype("datetime64[s]"))].reset_index(
        drop=True
    )
    out["cycle_counts"] = counts.rename(columns={"is_big_miss": "_is_big_miss"})
    return out


# --- Writing a run -------------------------------------------------------------------------


def write_run(
    cfg: Config,
    ref: Reference,
    tl: Timelines,
    sim: SimResult,
    as_of: date,
    run_id: str,
    day_only: bool,
) -> dict[str, int]:
    tables = build_tables(cfg, ref, tl, sim, as_of, day_only)
    tables, registry = apply_issues(cfg, tables, run_id, is_daily=day_only)
    extracted_at = np.datetime64(as_of + timedelta(days=1), "s") + np.timedelta64(2 * 3600, "s")

    counts = {}
    for name in TABLES:
        df = tables[name]
        if day_only and df.empty:
            continue
        write_parquet(to_arrow(df, name, extracted_at), cfg.raw_dir / name / f"{run_id}.parquet")
        counts[name] = len(df)

    write_parquet(
        pa.Table.from_pandas(registry, preserve_index=False).replace_schema_metadata(None),
        cfg.truth_dir / "planted_issues" / f"{run_id}.parquet",
    )
    return counts


def write_truth(cfg: Config, ref: Reference, model: DemandModel, sim: SimResult) -> None:
    """Ground truth the generator used. Never loaded into the warehouse."""
    truth = cfg.truth_dir

    def save(df: pd.DataFrame, name: str) -> None:
        write_parquet(
            pa.Table.from_pandas(df, preserve_index=False).replace_schema_metadata(None),
            truth / f"{name}.parquet",
        )

    save(ref.suppliers[["supplier_id", "country", "currency", "true_lead_time_mean_days",
                        "true_lead_time_sigma", "quoted_lead_time_days", "short_ship_prob",
                        "is_unreliable"]], "supplier_lead_times")  # fmt: skip
    p = ref.products
    save(
        pd.DataFrame(
            {
                "sku": p["sku"],
                "category": p["category"],
                "revenue_weight": p["revenue_weight"],
                "revenue_rank": p["revenue_rank"],
                "is_a_class_truth": p["is_a_class_truth"],
                "launch_date": p["launch_date"],
                "discontinued_date": p["discontinued_date"],
                "gut_feel_daily_demand": model.gut_rate.round(4),
                "expected_units_per_line": model.expected_qty,
            }
        ),
        "sku_demand_params",
    )
    c = ref.customers
    save(
        pd.DataFrame(
            {
                "customer_id": c["customer_id"],
                "customer_type": c["customer_type"],
                "order_rate_per_day": (c["order_rate_raw"] * model.rate_scale).round(5),
                "churn_date": c["churn_date"],
                "duplicate_of_customer_id": [
                    c["customer_id"].iat[d] if d >= 0 else None for d in c["duplicate_of_pos"]
                ],
            }
        ),
        "customers",
    )
    save(
        pd.DataFrame(
            {
                "show_name": [s.show_name for s in ref.shows],
                "warehouse_id": [s.warehouse_id for s in ref.shows],
                "start_date": [s.start_date for s in ref.shows],
                "end_date": [s.end_date for s in ref.shows],
                "demand_multiplier": ref.show_multipliers.round(4),
            }
        ),
        "gem_shows",
    )
    save(model.expected_daily, "expected_demand_daily")


def reset_output(cfg: Config) -> None:
    for path in (cfg.raw_dir, cfg.truth_dir):
        if path.exists():
            shutil.rmtree(path)
    if cfg.state_file.exists():
        cfg.state_file.unlink()


def read_state(cfg: Config) -> dict:
    if not cfg.state_file.exists():
        raise SystemExit(
            f"No generator state at {cfg.state_file}. Run the backfill first (make generate)."
        )
    return json.loads(cfg.state_file.read_text(encoding="utf-8"))


def write_state(cfg: Config, state: dict) -> None:
    cfg.state_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
