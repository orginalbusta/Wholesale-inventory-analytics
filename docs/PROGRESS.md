# Progress log

Update at the end of every phase: what was built, acceptance check results, known issues, next step.

| Phase | Status | Date | Notes |
|---|---|---|---|
| 0: Environment and skeleton | done | 2026-10-14 | All acceptance checks pass (see below) |
| 1: Synthetic data generator | done | 2026-10-14 | All acceptance checks pass; 18 pytest tests (see below) |
| 2: Ingestion (dlt) | done | 2026-10-14 | All acceptance checks pass; 7 new pytest tests (25 total) |
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
| `make generate SCALE=small` in < 60s | 1.4s (medium: ~5s) |
| `make test` | 18 passed in ~11s |
| Summary script prints sane stats | yes (`make summary`) |

Tests cover: byte-identical output for the same seed (and different output for another seed), volumes within ±25%, ledger never negative, movement IDs in timestamp order, fulfilled ≤ ordered, received ≤ ordered, ledger = counted qty after every cycle count, every PO line's local cost reconciles to USD through the FX seed, stockouts and dead stock exist, Pareto concentration, seasonality, quoted lead times optimistic, gem-show orders only in show windows, planted issues at configured rates and shaped correctly, extending the horizon doesn't rewrite history, simulate-day appends exactly one day.

**Generated data at a glance (seed 42)**
| | small | medium |
|---|---|---|
| Orders / order lines | 12,069 / 57,941 (targets 12k / 60k) | 40,595 / 287,545 (targets 40k / 300k) |
| Inventory movements | 57,827 | 306,405 |
| Top 20% of SKUs' share of revenue | 75.0% | 80.5% |
| Unit fill rate | 91.2% | 87.5% |
| Dead-stock SKUs / share of inventory cost | 9 / 9.9% | 109 / 9.4% |
| Received POs > 3 days later than quoted | 50.6% | 55.7% |
| gem_show share of orders | 8.4% | 11.6% |
| Synthetic revenue per year | ~$8M | ~$17M |

These are sanity statistics on synthetic data, not README findings; findings come from the dbt marts.

**Known issues / notes for later phases**
- Phase 3: `_extracted_at` is simulated, so source freshness against the wall clock will flag the backfill as stale (see DECISIONS.md).
- Phase 4: count ordered quantity on stockout-cancelled orders as demand (see DECISIONS.md).
- Medium volumes were cut to ~40k orders after review (was ~$53M/yr of synthetic revenue; now ~$17M/yr). See DECISIONS.md.

**Next:** Phase 2, ingestion with dlt.

## Phase 2: Ingestion with dlt (2026-10-14)

**Built**
- `ingestion/load_erp.py`: one dlt resource per table, Arrow tables straight from parquet, appended to `raw_erp.<table>` with `_run_id` and `_dlt_load_id`. Idempotency through `raw_erp.load_audit` (file SHA-256s); automatic full refresh when data was regenerated; `--full-refresh` flag.
- `ingestion/load_fred.py`: six FRED series into `raw_fred.observations` (merge on series_id + date, 90-day revision lookback). Official API with `FRED_API_KEY`, public CSV without one, warn-and-skip if offline.
- `ingestion/destinations.py`: `WAREHOUSE=duckdb` (default) or `snowflake` (key-pair auth from env; exercised in Phase 8).
- `.dlt/config.toml` (no secrets), `make clean` removes dlt's local state.

**Acceptance checks**
| Check | Result |
|---|---|
| `make load` populates DuckDB | yes: 11 raw_erp tables + load_audit, raw_fred.observations (4,024 rows) |
| Raw row counts match parquet | all 11 tables match (also a pytest) |
| Re-running is idempotent | second load: "raw_erp is up to date" (also a pytest; FRED merge idempotency tested with mocked HTTP) |
| `make simulate-day && make load` adds only the new day | loaded only the 2026-10-01 files (e.g. 52 order rows, 131 movements) (also a pytest) |

Timing: small ERP load 2.9s, FRED 4-6s (network); medium ERP load 3.6s for 679k rows.

**Notes for Phase 3**
- Raw keeps every extracted version, so staging must dedupe mutable tables on PK (latest `updated_at`, then `_extracted_at`).
- Add `product_price_history` (and optionally `load_audit`) to `_erp__sources.yml`; FRED `value` uses '' for missing in the CSV path and '.' in the API path.

**Next:** Phase 3, dbt sources, seeds, staging, snapshots.
