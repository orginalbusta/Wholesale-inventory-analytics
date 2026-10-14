"""Load synthetic ERP parquet files from data/raw/erp/ into the `raw_erp` schema with dlt.

Implementation plan (Phase 2):
    - One dlt resource per table, reading data/raw/erp/<table>/*.parquet.
    - write_disposition:
        merge on primary key  -> warehouses, suppliers, products, customers, sales_orders,
                                 sales_order_lines, purchase_orders, purchase_order_lines
        append                -> inventory_movements, cycle_counts
    - Track which run_id files were already loaded (dlt state or incremental on _extracted_at)
      so re-running is idempotent and simulate-day only loads new files.
    - Destination from env WAREHOUSE: "duckdb" (path from DUCKDB_PATH) or "snowflake".
    - Keep `purchase_orders.expected_arrival_date` as a STRING (planted issue 8 is parsed in dbt).

Run: uv run python -m ingestion.load_erp
"""

from __future__ import annotations

PRIMARY_KEYS: dict[str, str | None] = {
    "warehouses": "warehouse_id",
    "suppliers": "supplier_id",
    "products": "sku",
    "customers": "customer_id",
    "sales_orders": "order_id",
    "sales_order_lines": "order_line_id",
    "purchase_orders": "po_id",
    "purchase_order_lines": "po_line_id",
    "inventory_movements": None,  # append-only ledger
    "cycle_counts": None,  # append-only
}


def main() -> None:
    # TODO (Phase 2): implement per docstring and docs/02_architecture.md
    raise NotImplementedError("ERP load not implemented yet. See Phase 2.")


if __name__ == "__main__":
    main()
