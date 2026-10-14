"""Load `generator/config.yaml` and the seed files the generator shares with dbt.

The generator reads two dbt seeds directly so both layers agree on the same facts:
    - transform/seeds/gem_show_calendar.csv  (show windows drive demand and stock transfers)
    - transform/seeds/fx_static_rates.csv    (monthly FX used to create unit_cost_local)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# Seed files are always read from the repo, wherever output is written.
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "generator" / "config.yaml"


@dataclass(frozen=True)
class ScaleConfig:
    name: str
    start_date: date
    end_date: date
    n_customers: int
    n_skus: int
    n_suppliers: int
    target_orders: int
    target_order_lines: int

    @property
    def n_days(self) -> int:
        return (self.end_date - self.start_date).days + 1


@dataclass(frozen=True)
class Show:
    show_name: str
    warehouse_id: str
    start_date: date
    end_date: date

    @property
    def n_days(self) -> int:
        return (self.end_date - self.start_date).days + 1


@dataclass(frozen=True)
class Config:
    seed: int
    scale: ScaleConfig
    warehouses: list[dict]
    reference: dict
    demand: dict
    orders: dict
    purchasing: dict
    inventory: dict
    reference_changes: dict
    planted_issues: dict
    output: dict
    root: Path  # output root: data/ is written under it (the repo root by default)

    @property
    def raw_dir(self) -> Path:
        return self.root / self.output["raw_dir"]

    @property
    def truth_dir(self) -> Path:
        return self.root / self.output["truth_dir"]

    @property
    def state_file(self) -> Path:
        return self.root / self.output["state_file"]


def load_config(
    path: str | Path,
    scale: str,
    seed: int | None = None,
    root: str | Path = ".",
) -> Config:
    """Read config.yaml and resolve the chosen scale. `root` is where data/ is written."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    s = raw["scales"][scale]
    scale_cfg = ScaleConfig(
        name=scale,
        start_date=date.fromisoformat(s["start_date"]),
        end_date=date.fromisoformat(s["end_date"]),
        n_customers=int(s["n_customers"]),
        n_skus=int(s["n_skus"]),
        n_suppliers=int(s["n_suppliers"]),
        target_orders=int(s["target_orders"]),
        target_order_lines=int(s["target_order_lines"]),
    )
    return Config(
        seed=int(seed if seed is not None else raw["seed"]),
        scale=scale_cfg,
        warehouses=raw["warehouses"],
        reference=raw["reference"],
        demand=raw["demand"],
        orders=raw["orders"],
        purchasing=raw["purchasing"],
        inventory=raw["inventory"],
        reference_changes=raw["reference_changes"],
        planted_issues=raw["planted_issues"],
        output=raw["output"],
        root=Path(root),
    )


def load_shows(cfg: Config) -> list[Show]:
    """Read the gem show calendar seed (the same file dbt loads)."""
    df = pd.read_csv(REPO_ROOT / cfg.output["show_calendar_seed"])
    return [
        Show(
            show_name=row.show_name,
            warehouse_id=row.warehouse_id,
            start_date=date.fromisoformat(row.start_date),
            end_date=date.fromisoformat(row.end_date),
        )
        for row in df.itertuples()
    ]


class FxTable:
    """Monthly units-per-USD lookup from the committed FX seed (the same file dbt loads)."""

    def __init__(self, cfg: Config) -> None:
        df = pd.read_csv(REPO_ROOT / cfg.output["fx_seed"])
        self._rates = {
            (row.month[:7], row.currency): float(row.units_per_usd) for row in df.itertuples()
        }
        self._last_month = df["month"].max()[:7]

    def rate(self, day: date, currency: str) -> float:
        month = min(day.strftime("%Y-%m"), self._last_month)
        return self._rates[(month, currency)]

    def rates_for_days(self, days: np.ndarray, currency: str) -> np.ndarray:
        return np.array([self.rate(pd.Timestamp(d).date(), currency) for d in days])
