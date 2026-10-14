"""Build `transform/seeds/fx_static_rates.csv`: one monthly FX rate per currency.

This file is the single FX source shared by the generator (to create `unit_cost_local` on
purchase order lines) and by dbt (to convert those costs back to USD). Keeping one committed
file makes the generator byte-for-byte reproducible whether or not a FRED API key is set.
See docs/DECISIONS.md.

Sources:
    INR, BRL, CNY, MXN  monthly mean of FRED daily series (DEXINUS, DEXBZUS, DEXCHUS, DEXMXUS),
                        downloaded from FRED's public CSV endpoint (no API key needed)
    MGA, MAD            not published on FRED; rough approximations interpolated between a few
                        anchor points, labeled `approximation` in the `source` column
    USD                 1.0
Months after the last published FRED month are forward-filled (`forward_fill`).

Run (rarely; output is committed):
    uv run python scripts/build_fx_seed.py
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd=2023-01-01"
FRED_FX_SERIES = {"INR": "DEXINUS", "BRL": "DEXBZUS", "CNY": "DEXCHUS", "MXN": "DEXMXUS"}

# Approximate units per USD for currencies FRED does not publish. Not market data.
APPROX_ANCHORS = {
    "MGA": {"2023-01": 4450.0, "2024-06": 4500.0, "2025-01": 4700.0, "2025-07": 4450.0},
    "MAD": {"2023-01": 10.30, "2024-06": 9.95, "2025-01": 10.00, "2025-07": 9.10},
}

FIRST_MONTH = "2023-01"
LAST_MONTH = "2027-12"
OUTPUT = Path("transform/seeds/fx_static_rates.csv")


def fred_monthly_means(series: str) -> pd.Series:
    """Download a daily FRED series and return its monthly mean, indexed by month start."""
    response = requests.get(FRED_CSV_URL.format(series=series), timeout=60)
    response.raise_for_status()
    df = pd.read_csv(io.StringIO(response.text), na_values=["."])
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["value"])
    return df.set_index("date")["value"].resample("MS").mean()


def approximate_series(anchors: dict[str, float], months: pd.DatetimeIndex) -> pd.Series:
    """Linearly interpolate anchor values across months; hold the last anchor flat."""
    anchor_series = pd.Series(
        list(anchors.values()), index=pd.to_datetime(list(anchors.keys()))
    ).reindex(months.union(pd.to_datetime(list(anchors.keys()))))
    return anchor_series.interpolate(method="time").ffill().bfill().reindex(months)


def main() -> None:
    months = pd.date_range(FIRST_MONTH, LAST_MONTH, freq="MS")
    frames = []

    for currency, series in FRED_FX_SERIES.items():
        monthly = fred_monthly_means(series).reindex(months)
        source = pd.Series(f"FRED {series} monthly mean", index=months).where(
            monthly.notna(), "forward_fill"
        )
        frames.append(
            pd.DataFrame(
                {
                    "month": months,
                    "currency": currency,
                    "units_per_usd": monthly.ffill(),
                    "source": source,
                }
            )
        )

    for currency, anchors in APPROX_ANCHORS.items():
        frames.append(
            pd.DataFrame(
                {
                    "month": months,
                    "currency": currency,
                    "units_per_usd": approximate_series(anchors, months),
                    "source": "approximation",
                }
            )
        )

    frames.append(
        pd.DataFrame({"month": months, "currency": "USD", "units_per_usd": 1.0, "source": "base"})
    )

    out = pd.concat(frames, ignore_index=True).sort_values(["currency", "month"])
    out["month"] = out["month"].dt.strftime("%Y-%m-%d")
    out["units_per_usd"] = out["units_per_usd"].round(4)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT, index=False, lineterminator="\n")
    print(f"Wrote {len(out)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
