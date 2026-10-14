# Progress log

Update at the end of every phase: what was built, acceptance check results, known issues, next step.

| Phase | Status | Date | Notes |
|---|---|---|---|
| 0: Environment and skeleton | done | 2026-10-14 | All acceptance checks pass (see below) |
| 1: Synthetic data generator | done | 2026-10-14 | All acceptance checks pass; 18 pytest tests (see below) |
| 2: Ingestion (dlt) | not started | | |
| 3: dbt staging, seeds, snapshots | not started | | |
| 4: Intermediate and marts | not started | | |
| 5: Dashboard, docs site, README v1 | not started | | |
| 6: Orchestration and Docker | not started | | |
| 7: CI hardening | not started | | |
| 8: Snowflake target (optional) | not started | | |
| 9: Polish | not started | | |

## Phase 0: Environment and skeleton (2026-10-14)

**Built**
- `uv` project resolved on Python 3.12; dependency ranges tightened to current releases (`uv.lock` committed).
- dbt packages installed and locked (`transform/package-lock.yml`): dbt_utils 1.4.1, dbt_expectations 0.10.10 (+ dbt_date 0.21.0 as its dependency).
- pre-commit installed with trailing-whitespace, EOF, YAML, large-file, private-key, ruff, ruff-format and sqlfluff hooks.
- `.gitattributes` for LF line endings; `.python-version`.

**Acceptance checks**
| Check | Result |
|---|---|
| `uv sync --all-groups` + `dbt deps` (the `make setup` steps) on a fresh clone | pass |
| `ruff check`, `ruff format --check`, `sqlfluff lint` (the `make lint` steps) on a fresh clone | pass (0 violations) |
| `uv run dbt debug --project-dir transform --profiles-dir transform` | pass ("All checks passed!") |
| `dbt parse --show-all-deprecations` | 0 deprecation warnings (only the expected "unused config paths" warning: no intermediate/mart/snapshot models exist yet) |
| `pre-commit run --all-files` | pass |

**Known issues**
- GNU `make` is not installed on Harsh's Windows machine, so the checks were run as the exact commands from the Makefile. Install `make` to use the Makefile directly.
- Node 18.12 is installed; Evidence (Phase 5) needs a current LTS. Docker (Phase 6) is not installed.

**Next:** Phase 1, synthetic data generator.

## Phase 1: Synthetic data generator (2026-10-14)

**Built**
- `generator/` package: `config`, `randomness` (per-day seeded streams + stable hashes), `reference`, `timelines` (cost/price and customer-terms changes), `demand` (model + calibration + the naive buyer's estimate), `simulate` (day-by-day loop), `issues` (10 planted data-quality issues + registry), `writer` (as-of extracts, parquet, truth, state), `generate` (CLI), `summary` (`make summary`).
- `backfill` and `simulate-day` modes. simulate-day writes only that day's new and changed rows (new orders, late status updates to older orders, receipts, price changes).
- New ERP table `product_price_history`; new committed seed `transform/seeds/fx_static_rates.csv` (+ `scripts/build_fx_seed.py`); show calendar extended with Tucson 2027 for simulate-day.
- Ground truth in `data/_truth/`: supplier lead-time distributions, SKU demand weights and the buyer's gut-feel estimates, customer rates/churn/duplicates, show multipliers, expected demand per SKU-day, and a planted-issue registry per run.

**Acceptance checks**
| Check | Result |
|---|---|
| `make generate SCALE=small` in < 60s | 1.4s (medium: ~10s) |
| `make test` | 18 passed in ~11s |
| Summary script prints sane stats | yes (`make summary`) |

Tests cover: byte-identical output for the same seed (and different output for another seed), volumes within ±25%, ledger never negative, movement IDs in timestamp order, fulfilled ≤ ordered, received ≤ ordered, ledger = counted qty after every cycle count, every PO line's local cost reconciles to USD through the FX seed, stockouts and dead stock exist, Pareto concentration, seasonality, quoted lead times optimistic, gem-show orders only in show windows, planted issues at configured rates and shaped correctly, extending the horizon doesn't rewrite history, simulate-day appends exactly one day.

**Generated data at a glance (seed 42)**
| | small | medium |
|---|---|---|
| Orders / order lines | 12,069 / 57,941 (targets 12k / 60k) | 120,777 / 856,605 (targets 120k / 850k-1M) |
| Inventory movements | 57,827 | 830,413 |
| Top 20% of SKUs' share of revenue | 75.0% | 79.0% |
| Unit fill rate | 91.2% | 89.4% |
| Dead-stock SKUs / share of inventory cost | 9 / 9.9% | 78 / 5.9% |
| Received POs > 3 days later than quoted | 50.6% | 56.6% |
| gem_show share of orders | 8.4% | 11.7% |

These are sanity statistics on synthetic data, not README findings; findings come from the dbt marts.

**Known issues / notes for later phases**
- Phase 3: `_extracted_at` is simulated, so source freshness against the wall clock will flag the backfill as stale (see DECISIONS.md).
- Phase 4: count ordered quantity on stockout-cancelled orders as demand (see DECISIONS.md).
- Medium volumes imply roughly $50M/yr of revenue, high for a ~20-person distributor; open question for Harsh.

**Next:** Phase 2, ingestion with dlt.
