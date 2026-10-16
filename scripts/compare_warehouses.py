"""Check that DuckDB and Snowflake built the same marts from the same raw data.

For every table in the marts schema it compares the row count and the sum of every numeric
column. Run after loading the same generator snapshot into both warehouses and running
`dbt build` on each (see snowflake/README.md). Reads Snowflake credentials from .env.

    uv run --env-file .env python scripts/compare_warehouses.py
"""

import math
import os
import sys
from pathlib import Path

import duckdb
import snowflake.connector
from cryptography.hazmat.primitives import serialization

NUMERIC = (
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "DOUBLE",
    "FLOAT",
    "DECIMAL",
    "REAL",
)
REL_TOLERANCE = 1e-6  # floating-point sums can differ in the last digits between engines


def snowflake_connection():
    key = serialization.load_pem_private_key(
        Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).read_bytes(),
        password=(os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or "").encode() or None,
    )
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        private_key=key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def mart_columns(duck: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Numeric columns of every marts table, from DuckDB's catalog."""
    rows = duck.execute(
        "select table_name, column_name, data_type from information_schema.columns "
        "where table_schema = 'marts' order by table_name, ordinal_position"
    ).fetchall()
    tables: dict[str, list[str]] = {}
    for table, column, data_type in rows:
        tables.setdefault(table, [])
        if data_type.upper().startswith(NUMERIC):
            tables[table].append(column)
    return tables


def profile_sql(schema: str, table: str, columns: list[str]) -> str:
    sums = "".join(f", sum({c})" for c in columns)
    return f"select count(*){sums} from {schema}.{table}"


def close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=REL_TOLERANCE, abs_tol=1e-6)


def main() -> None:
    duck = duckdb.connect(os.getenv("DUCKDB_PATH", "warehouse/craftstones.duckdb"), read_only=True)
    sf = snowflake_connection().cursor()
    mismatches = 0
    tables = mart_columns(duck)
    for table, columns in tables.items():
        duck_row = duck.execute(profile_sql("marts", table, columns)).fetchone()
        sf_row = sf.execute(profile_sql("marts", table, columns)).fetchone()
        bad = [
            (name, d, s)
            for name, d, s in zip(["row_count", *columns], duck_row, sf_row, strict=True)
            if not close(d, s)
        ]
        status = "OK  " if not bad else "DIFF"
        print(f"{status} {table:<40} rows={duck_row[0]:>10,}  numeric columns={len(columns)}")
        for name, d, s in bad:
            print(f"       {name}: duckdb={d} snowflake={s}")
        mismatches += len(bad)
    print(f"\n{len(tables)} marts compared, {mismatches} mismatching value(s).")
    sys.exit(1 if mismatches else 0)


if __name__ == "__main__":
    main()
