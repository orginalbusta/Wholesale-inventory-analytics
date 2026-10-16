"""Pick the dlt destination from the environment, so both loaders share one setting.

    WAREHOUSE=duckdb     (default) DuckDB file at DUCKDB_PATH (default warehouse/craftstones.duckdb)
    WAREHOUSE=snowflake  Snowflake with key-pair auth from the SNOWFLAKE_* variables in .env.example
                         (optional target; setup in snowflake/README.md)

Secrets come only from environment variables / .env (git-ignored).
"""

from __future__ import annotations

import os
from pathlib import Path

import dlt
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINES_DIR = REPO_ROOT / ".dlt" / "pipelines"  # local dlt working state (git-ignored)


def default_pipelines_dir() -> Path:
    """dlt's local working state, one folder per warehouse.

    The ERP and FRED pipelines have the same names whichever warehouse they load into; separate
    folders keep a Snowflake run from picking up state that belongs to the DuckDB pipeline.
    """
    load_dotenv(REPO_ROOT / ".env")
    return PIPELINES_DIR / os.getenv("WAREHOUSE", "duckdb").lower()


def get_destination(duckdb_path: str | Path | None = None):
    """Return a configured dlt destination. `duckdb_path` overrides DUCKDB_PATH (used by tests)."""
    load_dotenv(REPO_ROOT / ".env")
    warehouse = os.getenv("WAREHOUSE", "duckdb").lower()

    if warehouse == "duckdb":
        path = Path(duckdb_path or os.getenv("DUCKDB_PATH", "warehouse/craftstones.duckdb"))
        path.parent.mkdir(parents=True, exist_ok=True)
        return dlt.destinations.duckdb(credentials=str(path))

    if warehouse == "snowflake":
        key_path = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
        return dlt.destinations.snowflake(
            credentials={
                "host": os.environ["SNOWFLAKE_ACCOUNT"],
                "username": os.environ["SNOWFLAKE_USER"],
                "database": os.environ["SNOWFLAKE_DATABASE"],
                "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
                "role": os.environ["SNOWFLAKE_ROLE"],
                "private_key": Path(key_path).read_text(encoding="utf-8"),
                "private_key_passphrase": os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
            }
        )

    raise SystemExit(f"Unknown WAREHOUSE={warehouse!r}; expected 'duckdb' or 'snowflake'.")
