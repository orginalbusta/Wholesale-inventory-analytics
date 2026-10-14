"""Load synthetic ERP parquet files from data/raw/erp/ into the `raw_erp` schema with dlt.

The raw layer is an append-only record of every extract, exactly as the source sent it:
    - Each file data/raw/erp/<table>/<run_id>.parquet is appended to raw_erp.<table>, with a
      `_run_id` column (and dlt's `_dlt_load_id`) for lineage.
    - Mutable tables (orders, purchase orders, products, customers) therefore keep every
      version that was extracted, including re-extracted duplicates and late status updates.
      dbt staging picks the latest version per primary key (see docs/DECISIONS.md).

Idempotency comes from `raw_erp.load_audit`, written in the same load: one row per file with
its SHA-256. Re-running skips files already loaded, so `make simulate-day && make load` adds
only the new day. If a file was regenerated (same run_id, different hash, e.g. a fresh
`make generate`), the raw_erp dataset is dropped and everything is reloaded.

Run: uv run python -m ingestion.load_erp [--full-refresh]
"""

from __future__ import annotations

import argparse
import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import dlt
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion.destinations import PIPELINES_DIR, get_destination

PIPELINE_NAME = "craftstones_erp"
DATASET_NAME = "raw_erp"
DEFAULT_RAW_DIR = Path("data/raw/erp")

# Primary keys, for documentation and for dbt's uniqueness tests in staging. Raw keeps every
# extracted version, so these are NOT unique in raw_erp.
PRIMARY_KEYS: dict[str, str | None] = {
    "warehouses": "warehouse_id",
    "suppliers": "supplier_id",
    "products": "sku",
    "product_price_history": "price_change_id",
    "customers": "customer_id",
    "sales_orders": "order_id",
    "sales_order_lines": "order_line_id",
    "purchase_orders": "po_id",
    "purchase_order_lines": "po_line_id",
    "inventory_movements": "movement_id",
    "cycle_counts": "count_id",
}


@dataclass(frozen=True)
class RawFile:
    table: str
    run_id: str
    path: Path
    sha256: str
    rows: int


def discover_files(raw_dir: Path) -> list[RawFile]:
    """All extract files, ordered so the backfill loads before daily runs."""
    files = []
    for table_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        for path in sorted(
            table_dir.glob("*.parquet"), key=lambda p: (p.stem != "backfill", p.stem)
        ):
            files.append(
                RawFile(
                    table=table_dir.name,
                    run_id=path.stem,
                    path=path,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    rows=pq.read_metadata(path).num_rows,
                )
            )
    return files


def loaded_files(pipeline: dlt.Pipeline) -> dict[tuple[str, str], str]:
    """(table, run_id) -> sha256 for every file already recorded in raw_erp.load_audit."""
    try:
        with pipeline.sql_client() as client:
            rows = client.execute_sql(
                f"select table_name, run_id, file_sha256 from {DATASET_NAME}.load_audit"
            )
    except Exception:  # dataset or table doesn't exist yet: nothing loaded
        return {}
    return {(t, r): h for t, r, h in rows}


def _timestamp_hints(schema: pa.Schema) -> dict:
    """Keep timestamps timezone-naive in the warehouse (dlt defaults to TIMESTAMPTZ)."""
    return {
        f.name: {"data_type": "timestamp", "timezone": False}
        for f in schema
        if pa.types.is_timestamp(f.type)
    }


def _table_resource(table: str, files: list[RawFile]):
    columns = _timestamp_hints(pq.read_schema(files[0].path))

    @dlt.resource(name=table, write_disposition="append", columns=columns)
    def extract():
        for f in files:
            data = pq.read_table(f.path)
            yield data.append_column("_run_id", pa.array([f.run_id] * len(data), pa.string()))

    return extract()


@dlt.resource(
    name="load_audit",
    write_disposition="append",
    columns={"loaded_at": {"data_type": "timestamp", "timezone": False}},
)
def _audit_resource(files: list[RawFile], loaded_at: datetime):
    yield [
        {
            "table_name": f.table,
            "run_id": f.run_id,
            "file_sha256": f.sha256,
            "row_count": f.rows,
            "loaded_at": loaded_at,
        }
        for f in files
    ]


@dlt.source(name="erp")
def erp_source(files: list[RawFile]):
    by_table: dict[str, list[RawFile]] = {}
    for f in files:
        by_table.setdefault(f.table, []).append(f)
    resources = [_table_resource(t, fs) for t, fs in by_table.items()]
    loaded_at = datetime.now(UTC).replace(tzinfo=None)
    return [*resources, _audit_resource(files, loaded_at)]


def make_pipeline(
    duckdb_path: str | Path | None = None, pipelines_dir: Path | None = None
) -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination=get_destination(duckdb_path),
        dataset_name=DATASET_NAME,
        pipelines_dir=str(pipelines_dir or PIPELINES_DIR),
    )


def load_erp(
    raw_dir: Path = DEFAULT_RAW_DIR,
    duckdb_path: str | Path | None = None,
    pipelines_dir: Path | None = None,
    full_refresh: bool = False,
) -> dict[str, int]:
    """Load new extract files. Returns rows loaded per table (empty if nothing new)."""
    files = discover_files(raw_dir)
    if not files:
        raise SystemExit(f"No parquet files under {raw_dir}. Run `make generate` first.")

    pipeline = make_pipeline(duckdb_path, pipelines_dir)
    already = {} if full_refresh else loaded_files(pipeline)
    regenerated = [
        f
        for f in files
        if (f.table, f.run_id) in already and already[(f.table, f.run_id)] != f.sha256
    ]
    if regenerated:
        print(
            f"{len(regenerated)} file(s) changed since they were loaded (data was regenerated): full refresh."
        )
        full_refresh, already = True, {}

    new_files = [f for f in files if (f.table, f.run_id) not in already]
    if not new_files:
        print("raw_erp is up to date; nothing to load.")
        return {}

    pipeline.run(erp_source(new_files), refresh="drop_sources" if full_refresh else None)

    counts: dict[str, int] = {}
    for f in new_files:
        counts[f.table] = counts.get(f.table, 0) + f.rows
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Load data/raw/erp into raw_erp with dlt.")
    parser.add_argument(
        "--full-refresh", action="store_true", help="Drop raw_erp and reload all files"
    )
    args = parser.parse_args()
    started = time.perf_counter()
    counts = load_erp(full_refresh=args.full_refresh)
    for table, n in sorted(counts.items()):
        print(f"  {table:<24} {n:>10,} rows")
    print(f"load_erp finished in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
