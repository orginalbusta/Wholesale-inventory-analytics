"""CLI entry point for the synthetic data generator.

Usage:
    uv run python -m generator.generate --scale small --mode backfill
    uv run python -m generator.generate --scale small --mode simulate-day

Implementation plan (Phase 1). Suggested module layout:
    generator/
      config.py        load + validate config.yaml, resolve scale
      reference.py     warehouses, suppliers (+ hidden lead-time truth), products, customers
      demand.py        per-SKU daily expected demand (base x trend x seasonality x show x lifecycle x price)
      simulate.py      day-by-day loop: demand -> orders -> fulfillment from inventory -> naive purchasing
                       -> PO arrivals -> transfers to/from show warehouses -> cycle counts -> ledger
      issues.py        apply planted data-quality issues AFTER the clean simulation; record IDs in _truth
      writer.py        parquet output per table per run_id, _extracted_at, truth files, state file
      state.py         serialize/restore simulation state for simulate-day mode

Key invariants (test these in tests/test_generator.py):
    - Same seed + scale -> identical outputs.
    - True (pre-issue) inventory never goes negative.
    - quantity_fulfilled <= quantity; stockouts and dead stock both occur.
    - Planted issues appear at configured rates and are listed in data/_truth/planted_issues.parquet.
"""

from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scale", choices=["small", "medium"], default="small")
    parser.add_argument("--mode", choices=["backfill", "simulate-day"], default="backfill")
    parser.add_argument("--config", default="generator/config.yaml")
    parser.add_argument("--seed", type=int, default=None, help="Override config seed")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # TODO (Phase 1): implement per docs/03_data_spec.md
    raise NotImplementedError(
        f"Generator not implemented yet (scale={args.scale}, mode={args.mode}). See Phase 1."
    )


if __name__ == "__main__":
    main()
