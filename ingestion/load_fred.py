"""Load public FRED series into `raw_fred.observations` with dlt.

Long format, one row per series per date: series_id, date, value (string exactly as FRED
sends it; '.' or '' means missing), realtime_start, fetched_via.

Sources, in order of preference:
    1. The official FRED API, when FRED_API_KEY is set (free key; see .env.example).
    2. FRED's public CSV download (fredgraph.csv), which needs no key.
If FRED can't be reached at all, the loader logs a warning and exits 0. Nothing downstream
depends on it to build: PO costs are converted with the committed FX seed
(transform/seeds/fx_static_rates.csv); these series add macro context and future forecast
regressors.

Incremental: each run re-fetches from 90 days before the latest loaded date per series
(FRED revises recent values) and merges on (series_id, date), so re-running never
duplicates rows.

Run: uv run python -m ingestion.load_fred
"""

from __future__ import annotations

import csv
import io
import os
import time
from datetime import date, timedelta
from pathlib import Path

import dlt
import requests
from dotenv import load_dotenv

from ingestion.destinations import PIPELINES_DIR, REPO_ROOT, get_destination

PIPELINE_NAME = "craftstones_fred"
DATASET_NAME = "raw_fred"
OBSERVATION_START = date(2023, 1, 1)
REVISION_LOOKBACK_DAYS = 90
API_URL = "https://api.stlouisfed.org/fred/series/observations"
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# All six verified live on FRED on 2026-10-14.
FRED_SERIES: dict[str, str] = {
    "DEXINUS": "Indian rupees per USD (daily)",
    "DEXBZUS": "Brazilian reals per USD (daily)",
    "DEXCHUS": "Chinese yuan per USD (daily)",
    "DEXMXUS": "Mexican pesos per USD (daily)",
    "RSXFS": "US advance retail sales excl. food services (monthly)",
    "UMCSENT": "University of Michigan consumer sentiment (monthly)",
}


def fetch_via_api(series_id: str, start: date, api_key: str) -> list[dict]:
    response = requests.get(
        API_URL,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start.isoformat(),
        },
        timeout=60,
    )
    response.raise_for_status()
    return [
        {
            "series_id": series_id,
            "date": date.fromisoformat(obs["date"]),
            "value": obs["value"],
            "realtime_start": date.fromisoformat(obs["realtime_start"]),
            "fetched_via": "api",
        }
        for obs in response.json()["observations"]
    ]


def fetch_via_csv(series_id: str, start: date) -> list[dict]:
    response = requests.get(
        CSV_URL, params={"id": series_id, "cosd": start.isoformat()}, timeout=60
    )
    response.raise_for_status()
    reader = csv.reader(io.StringIO(response.text))
    next(reader)  # header: observation_date,<SERIES_ID>
    return [
        {
            "series_id": series_id,
            "date": date.fromisoformat(row[0]),
            "value": row[1],
            "realtime_start": None,
            "fetched_via": "public_csv",
        }
        for row in reader
        if row
    ]


def latest_loaded_dates(pipeline: dlt.Pipeline) -> dict[str, date]:
    try:
        with pipeline.sql_client() as client:
            rows = client.execute_sql(
                f"select series_id, max(date) from {DATASET_NAME}.observations group by 1"
            )
    except Exception:  # first run: table doesn't exist yet
        return {}
    return {s: d for s, d in rows}


def fetch_all(start_by_series: dict[str, date], api_key: str | None) -> list[dict]:
    rows: list[dict] = []
    for series_id, start in start_by_series.items():
        if api_key:
            rows += fetch_via_api(series_id, start, api_key)
        else:
            rows += fetch_via_csv(series_id, start)
    return rows


@dlt.resource(
    name="observations",
    write_disposition="merge",
    primary_key=("series_id", "date"),
    columns={
        "value": {"data_type": "text"},
        "realtime_start": {"data_type": "date", "nullable": True},
    },
)
def observations(rows: list[dict]):
    yield rows


def load_fred(duckdb_path: str | Path | None = None, pipelines_dir: Path | None = None) -> int:
    """Fetch and merge FRED series. Returns rows fetched (0 if FRED was unreachable)."""
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("FRED_API_KEY") or None
    pipeline = dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination=get_destination(duckdb_path),
        dataset_name=DATASET_NAME,
        pipelines_dir=str(pipelines_dir or PIPELINES_DIR),
    )
    latest = latest_loaded_dates(pipeline)
    start_by_series = {
        s: max(OBSERVATION_START, latest[s] - timedelta(days=REVISION_LOOKBACK_DAYS))
        if s in latest
        else OBSERVATION_START
        for s in FRED_SERIES
    }
    print(
        "Fetching FRED via",
        "the API" if api_key else "the public CSV endpoint (no FRED_API_KEY set)",
    )

    try:
        rows = fetch_all(start_by_series, api_key)
    except requests.RequestException as exc:
        print(
            f"WARNING: could not reach FRED ({exc.__class__.__name__}); skipping. dbt uses the FX seed."
        )
        return 0

    pipeline.run(observations(rows))
    return len(rows)


def main() -> None:
    started = time.perf_counter()
    n = load_fred()
    print(f"load_fred: {n:,} observations fetched in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
