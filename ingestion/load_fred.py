"""Load public FRED series into `raw_fred.observations` with dlt.

Implementation plan (Phase 2):
    - Series list below (verify each still exists on FRED before relying on it).
    - Long format: series_id, date, value (string; FRED uses '.' for missing), realtime_start.
    - Incremental on date per series; merge on (series_id, date).
    - If FRED_API_KEY is missing: log a warning and exit 0. dbt falls back to seeds/fx_static_rates.csv.
    - Cache responses to data/raw/fred/ so the generator can use the same FX values for unit_cost_local.

Run: uv run python -m ingestion.load_fred
"""

from __future__ import annotations

FRED_SERIES: dict[str, str] = {
    "DEXINUS": "Indian rupees per USD (daily)",
    "DEXBZUS": "Brazilian reals per USD (daily)",
    "DEXCHUS": "Chinese yuan per USD (daily)",
    "DEXMXUS": "Mexican pesos per USD (daily)",
    "RSXFS": "US advance retail sales excl. food services (monthly)",
    "UMCSENT": "University of Michigan consumer sentiment (monthly)",
}


def main() -> None:
    # TODO (Phase 2): implement per docstring
    raise NotImplementedError("FRED load not implemented yet. See Phase 2.")


if __name__ == "__main__":
    main()
