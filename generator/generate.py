"""CLI entry point for the synthetic data generator.

Usage:
    uv run python -m generator.generate --scale small --mode backfill
    uv run python -m generator.generate --scale small --mode simulate-day
    uv run python -m generator.generate --scale small --mode catch-up --until yesterday

Modes:
    backfill      wipe data/raw/erp and data/_truth, simulate start_date..end_date, write
                  every table as of end_date (run_id "backfill") plus ground truth
    simulate-day  advance one day past the last run recorded in data/raw/_state.json and write
                  only that day's new and changed rows (run_id "<YYYY-MM-DD>")
    catch-up      like simulate-day for every missing day through --until (default:
                  yesterday), simulating once; keeps the nightly-refreshed site current

simulate-day re-runs the whole simulation up to the new day instead of restoring a pickled
state. Every day draws from its own random stream (generator/randomness.py), so the re-run
reproduces all earlier days exactly and only the new day is new.

Module layout:
    config.py      config.yaml + shared seeds (show calendar, FX rates)
    randomness.py  per-day random streams and stable hashes
    reference.py   warehouses, suppliers, products, customers (+ hidden truth)
    timelines.py   cost/price changes and customer term changes over time
    demand.py      demand model, calibration, the naive buyer's demand estimate
    simulate.py    day-by-day loop: orders -> fulfillment -> transfers -> counts -> purchasing
    issues.py      planted data-quality issues + registry
    writer.py      as-of extracts, parquet output, truth files, state file
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from generator.config import DEFAULT_CONFIG_PATH, load_config
from generator.demand import build_demand_model
from generator.reference import build_reference
from generator.simulate import run_simulation
from generator.timelines import build_timelines
from generator.writer import read_state, reset_output, write_run, write_state, write_truth


def simulate_through(cfg, horizon_end: date):
    """Build reference data and run the simulation from start_date through `horizon_end`."""
    ref = build_reference(cfg)
    tl = build_timelines(cfg, ref, horizon_end)
    model = build_demand_model(cfg, ref, tl)
    sim = run_simulation(cfg, ref, tl, model)
    return ref, tl, model, sim


def backfill(cfg) -> dict[str, int]:
    reset_output(cfg)
    end = cfg.scale.end_date
    ref, tl, model, sim = simulate_through(cfg, end)
    counts = write_run(cfg, ref, tl, sim, end, "backfill", day_only=False)
    write_truth(cfg, ref, model, sim)
    write_state(
        cfg,
        {
            "scale": cfg.scale.name,
            "seed": cfg.seed,
            "start_date": cfg.scale.start_date.isoformat(),
            "as_of_date": end.isoformat(),
            "runs": ["backfill"],
        },
    )
    return counts


def catch_up(cfg, until: date | None = None) -> dict[str, int]:
    """Write one day-only extract for every day after the last run, through `until`
    (default: just the next day). Simulates once, however many days are missing."""
    state = read_state(cfg)
    if state["scale"] != cfg.scale.name or state["seed"] != cfg.seed:
        raise SystemExit(
            f"State is for scale={state['scale']} seed={state['seed']}; "
            f"rerun the backfill or pass --scale {state['scale']}."
        )
    last = date.fromisoformat(state["as_of_date"])
    until = until or last + timedelta(days=1)
    if until <= last:
        print(f"Already simulated through {last}; nothing to do.")
        return {}
    ref, tl, _, sim = simulate_through(cfg, until)
    totals: dict[str, int] = {}
    day = last + timedelta(days=1)
    while day <= until:
        run_id = day.isoformat()
        for table, n in write_run(cfg, ref, tl, sim, day, run_id, day_only=True).items():
            totals[table] = totals.get(table, 0) + n
        state["as_of_date"] = run_id
        state["runs"].append(run_id)
        write_state(cfg, state)
        day += timedelta(days=1)
    return totals


def simulate_day(cfg) -> dict[str, int]:
    """Advance exactly one day."""
    return catch_up(cfg)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synthetic ERP data generator (all data is fictional)."
    )
    parser.add_argument("--scale", choices=["small", "medium"], default="small")
    parser.add_argument(
        "--mode", choices=["backfill", "simulate-day", "catch-up"], default="backfill"
    )
    parser.add_argument(
        "--until",
        default="yesterday",
        help="catch-up only: last day to simulate, YYYY-MM-DD or 'yesterday' (UTC)",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--seed", type=int, default=None, help="Override config seed")
    parser.add_argument("--output-root", default=".", help="Directory that data/ is written under")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config, args.scale, seed=args.seed, root=Path(args.output_root))
    started = time.perf_counter()
    if args.mode == "backfill":
        counts = backfill(cfg)
    elif args.mode == "simulate-day":
        counts = simulate_day(cfg)
    else:
        until = (
            datetime.now(UTC).date() - timedelta(days=1)
            if args.until == "yesterday"
            else date.fromisoformat(args.until)
        )
        counts = catch_up(cfg, until)
    elapsed = time.perf_counter() - started
    print(f"{args.mode} ({args.scale}, seed {cfg.seed}) finished in {elapsed:.1f}s")
    for table, n in counts.items():
        print(f"  {table:<24} {n:>10,}")


if __name__ == "__main__":
    main()
