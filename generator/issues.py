"""Planted data-quality issues (docs/03_data_spec.md, issues 1-10) and their registry.

Issues created inside the simulation (they change what physically happened or who ordered):
    1  duplicate customers ............ reference.build_customers / simulate (order reassignment)
    6  returns as negative lines ...... simulate
    9  orphan order lines ............. simulate
    10 big-miss cycle counts .......... simulate

Issues applied here, to the rows of each extraction run (they only change how data is keyed):
    2  inconsistent category labels
    3  SKU code variants on order lines
    4  duplicate rows from re-extraction (identical copies or stale older versions)
    7  null or malformed emails
    8  mixed date formats in purchase_orders.expected_arrival_date
    5  late-arriving status updates are inherent to simulate-day runs and are logged here

Selection uses stable hashes of record IDs, so a record gets the same issue in every run.
Every affected record is listed in data/_truth/planted_issues/<run_id>.parquet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator.config import Config
from generator.randomness import stable_uniform_array

ISSUE_NAMES = {
    1: "duplicate_customer",
    2: "inconsistent_category_label",
    3: "sku_code_variant",
    4: "reextracted_duplicate_order",
    5: "late_arriving_status_update",
    6: "negative_quantity_return_line",
    7: "bad_or_null_email",
    8: "mixed_date_format",
    9: "orphan_order_line",
    10: "cycle_count_big_miss",
}

# Messy spellings that still map to the canonical category after trim + lowercase +
# whitespace collapse + transform/seeds/category_mapping.csv.
CATEGORY_VARIANTS = {
    "Polished Stones": ["polished stones", "Polished  Stones ", "POLISHED", " polished stone"],
    "Rough Minerals": ["rough minerals", "ROUGH", "Rough Mineral ", "rough  minerals"],
    "Crystal Clusters": ["crystal clusters", "CLUSTERS", "Crystal Cluster ", " crystal  clusters"],
    "Tumbled Stones": ["tumbled stones", "TUMBLED", "Tumbled  Stone", "tumbled stones "],
    "Jewelry Components": [
        "jewelry components",
        "JEWELRY",
        " Jewellery Components",
        "Jewelry  Components",
    ],
    "Decor & Landscape": ["decor and landscape", "DECOR & LANDSCAPE", "Decor ", "landscape"],
}


def _pick(seed: int, prefix: str, keys, options: list[str]) -> list[str]:
    u = stable_uniform_array(seed, prefix, keys)
    return [options[int(x * len(options))] for x in u]


def sku_variant(sku: str, choice: float) -> str:
    """Return a mis-keyed version of a canonical SKU like AMT-PLS-0042."""
    variants = [
        sku.lower(),
        sku.replace("-", ""),
        sku.replace("-", "").lower(),
        f" {sku} ",
        sku.replace("-", "_"),
        sku.title(),
    ]
    return variants[int(choice * len(variants))]


def malformed_email(email: str, choice: float) -> str | None:
    local, _, domain = email.partition("@")
    variants = [
        None,
        None,
        f"{local}@",
        f"{local} at {domain}",
        f"{local}@{domain.split('.')[0]}",
        f"{local}@@{domain}",
    ]
    return variants[int(choice * len(variants))]


def apply_issues(
    cfg: Config, tables: dict[str, pd.DataFrame], run_id: str, is_daily: bool
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    rates = cfg.planted_issues
    seed = cfg.seed
    registry: list[dict] = []

    def log(issue: int, table: str, ids, details=None) -> None:
        ids = list(ids)
        details = list(details) if details is not None else [""] * len(ids)
        for rid, det in zip(ids, details, strict=True):
            registry.append(
                {
                    "issue_no": issue,
                    "issue_name": ISSUE_NAMES[issue],
                    "table_name": table,
                    "record_id": str(rid),
                    "detail": str(det),
                    "run_id": run_id,
                }
            )

    # 1. Duplicate customers (records created in the simulation) and orders keyed to them
    cust = tables["customers"]
    dups = cust[cust["_duplicate_of_id"].notna()]
    log(1, "customers", dups["customer_id"], "duplicate of " + dups["_duplicate_of_id"])
    orders = tables["sales_orders"]
    moved = orders[orders["customer_id"] != orders["_canonical_customer_id"]]
    log(1, "sales_orders", moved["order_id"], "keyed to duplicate " + moved["customer_id"])

    # 2. Inconsistent category labels
    prod = tables["products"].copy()
    u = stable_uniform_array(seed, "category", prod["sku"])
    hit = u < rates["inconsistent_category_labels"]
    if hit.any():
        variants = [
            CATEGORY_VARIANTS[c][int(x * len(CATEGORY_VARIANTS[c]))]
            for c, x in zip(
                prod.loc[hit, "category"],
                stable_uniform_array(seed, "category_variant", prod.loc[hit, "sku"]),
                strict=True,
            )
        ]
        prod.loc[hit, "category"] = variants
        log(2, "products", prod.loc[hit, "sku"], prod.loc[hit, "category"])
    tables["products"] = prod

    # 7. Null or malformed emails
    cust = cust.copy()
    u = stable_uniform_array(seed, "email", cust["customer_id"])
    hit = u < rates["bad_or_null_emails"]
    if hit.any():
        choice = stable_uniform_array(seed, "email_variant", cust.loc[hit, "customer_id"])
        cust.loc[hit, "contact_email"] = [
            malformed_email(e, x)
            for e, x in zip(cust.loc[hit, "contact_email"], choice, strict=True)
        ]
        log(
            7,
            "customers",
            cust.loc[hit, "customer_id"],
            cust.loc[hit, "contact_email"].fillna("<null>"),
        )
    tables["customers"] = cust

    # 3, 6, 9. Order line issues
    lines = tables["sales_order_lines"].copy()
    normal = (lines["_line_kind"] == 0).to_numpy()
    u = stable_uniform_array(seed, "sku_variant", lines["order_line_id"])
    hit = normal & (u < rates["sku_code_variants"])
    if hit.any():
        choice = stable_uniform_array(seed, "sku_variant_kind", lines.loc[hit, "order_line_id"])
        lines.loc[hit, "sku"] = [
            sku_variant(s, x) for s, x in zip(lines.loc[hit, "sku"], choice, strict=True)
        ]
        log(3, "sales_order_lines", lines.loc[hit, "order_line_id"], lines.loc[hit, "sku"])
    neg = lines[lines["_line_kind"] == 1]
    log(6, "sales_order_lines", neg["order_line_id"], neg["quantity"].astype(str))
    orphan = lines[lines["_line_kind"] == 2]
    log(9, "sales_order_lines", orphan["order_line_id"], orphan["sku"])
    tables["sales_order_lines"] = lines

    # 4. Re-extracted duplicate order rows: an identical copy, or a stale older version
    u = stable_uniform_array(seed, f"reextract|{run_id}", orders["order_id"])
    hit = u < rates["reextracted_duplicate_orders"]
    if hit.any():
        copies = orders[hit].copy()
        stale = stable_uniform_array(seed, f"reextract_stale|{run_id}", copies["order_id"]) < 0.5
        stale &= (copies["status"] != "placed").to_numpy()
        copies.loc[stale, "status"] = "placed"
        copies.loc[stale, "ship_date"] = pd.NaT
        copies.loc[stale, "cancel_reason"] = None
        copies.loc[stale, "updated_at"] = copies.loc[stale, "_placed_ts"]
        log(
            4,
            "sales_orders",
            copies["order_id"],
            np.where(stale, "stale older version", "identical copy"),
        )
        orders = pd.concat([orders, copies], ignore_index=True)
        orders = orders.sort_values(["order_id", "updated_at"], kind="stable").reset_index(
            drop=True
        )

    # 5. Late-arriving status updates (daily runs re-send orders placed on earlier days)
    if is_daily:
        late = orders[orders["order_date"] < orders["_run_date"]]
        log(5, "sales_orders", late["order_id"].unique())
    tables["sales_orders"] = orders

    # 8. Mixed date formats in purchase_orders.expected_arrival_date
    po = tables["purchase_orders"].copy()
    u = stable_uniform_array(seed, "date_format", po["po_id"])
    hit = u < rates["mixed_date_formats"]
    dates = pd.to_datetime(po["expected_arrival_date"])
    po["expected_arrival_date"] = np.where(
        hit, dates.dt.strftime("%m/%d/%Y"), dates.dt.strftime("%Y-%m-%d")
    )
    log(8, "purchase_orders", po.loc[hit, "po_id"], po.loc[hit, "expected_arrival_date"])
    tables["purchase_orders"] = po

    # 10. Big-miss cycle counts
    cc = tables["cycle_counts"]
    big = cc[cc["_is_big_miss"]]
    log(10, "cycle_counts", big["count_id"], (big["counted_qty"] - big["system_qty"]).astype(str))

    registry_df = pd.DataFrame(
        registry,
        columns=["issue_no", "issue_name", "table_name", "record_id", "detail", "run_id"],
    )
    return tables, registry_df
