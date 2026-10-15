# Progress log

Update at the end of every phase: what was built, acceptance check results, known issues, next step.

| Phase | Status | Date | Notes |
|---|---|---|---|
| 0: Environment and skeleton | done | 2026-10-14 | All acceptance checks pass (see below) |
| 1: Synthetic data generator | done | 2026-10-14 | All acceptance checks pass; 18 pytest tests (see below) |
| 2: Ingestion (dlt) | done | 2026-10-14 | All acceptance checks pass; 7 new pytest tests (25 total) |
| 3: dbt staging, seeds, snapshots | done | 2026-10-15 | All acceptance checks pass; 13 new pytest tests (38 total) |
| 4: Intermediate and marts | done | 2026-10-15 | All acceptance checks pass; 50 pytest tests; CI enabled |
| 5: Dashboard, docs site, README v1 | done | 2026-10-15 | Both sites live on GitHub Pages; nightly refresh; README v1 with real findings |
| 6: Orchestration (Dagster) and Docker | done | 2026-10-15 | 61 assets with end-to-end lineage; Materialize all succeeds; Docker stack checked in CI; 57 pytest tests |
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

## Phase 3: dbt sources, seeds, staging, snapshots (2026-10-15)

**Built**
- Sources: 12 ERP tables (added `product_price_history`, `load_audit`) with freshness on orders and movements; FRED observations.
- Seeds: `gem_show_calendar`, `category_mapping`, `fx_static_rates`, `abc_xyz_policy`, with column types, descriptions and key tests (`_seeds.yml`).
- 12 staging views: 11 ERP + FRED, every column described. Each dedupes to the latest version per key.
- Macros: `normalize_sku`, `parse_mixed_date`, `generate_schema_name`, plus cross-db helpers (`regexp_replace_all`, `regexp_full_match`, `normalize_label`).
- Snapshots: `snap_products` (timestamp strategy), `snap_customers` (check on credit_terms, sales_rep_id).
- Tests: 95 data tests, 1 singular test (duplicate emails), 5 dbt unit tests (SKU normalization, return lines, mixed dates, latest-version dedupe, category mapping).
- `tests/test_dbt_staging.py`: builds a fresh warehouse (backfill + simulate-day) and checks all 10 planted issues against `data/_truth`.

**How each planted issue is handled**
| # | Issue | Fixed in staging | Caught by test |
|---|---|---|---|
| 1 | Duplicate customers | (resolved in Phase 4 int model) | `assert_no_duplicate_customer_emails` (warn) |
| 2 | Inconsistent category labels | normalize + `category_mapping` seed | `not_null` + `accepted_values` on category; unit test |
| 3 | SKU code variants | `normalize_sku()` | relationships to products; unit test |
| 4 | Re-extracted duplicate orders | latest-version dedupe | `unique` on order_id; unit test |
| 5 | Late status updates | latest-version dedupe | pytest vs. truth |
| 6 | Returns as negative lines | `is_return_line` + positive quantities | quantity >= 0; unit test |
| 7 | Null / malformed emails | lowercase + `is_email_valid` | regex test (warn) |
| 8 | Mixed date formats | `parse_mixed_date()` | `not_null` on parsed date; unit test |
| 9 | Orphan order lines | (quarantined in Phase 4) | relationships test (warn) |
| 10 | Big-miss cycle counts | `variance_pct` | variance between -15% and +5% (warn) |

**Acceptance checks**
| Check | Result |
|---|---|
| `dbt build --select staging+ seeds snapshots` | PASS=100, WARN=4, ERROR=0 (full `dbt build`: PASS=114, WARN=4, ERROR=0 in ~2.5s of dbt time) |
| The 4 warnings are exactly the planted issues | duplicate emails (4), malformed emails (5), orphan SKUs (71), big-miss counts (7), all matching the truth registry |
| Every planted issue fixed or caught, cross-checked with truth | `tests/test_dbt_staging.py`: 13 passed |
| Build survives a missing FRED source | tested by dropping `raw_fred` |
| sqlfluff, ruff, zero dbt deprecation warnings | pass |

**Known issues**
- `dbt source freshness` reports ERROR STALE: extraction time is simulated and the data ends 2026-10-02. Plan: a catch-up mode for simulate-day used by the nightly job (Phase 5/6). See DECISIONS.md.

**Next:** Phase 4, intermediate models and marts.

## Phase 4: Intermediate and marts (2026-10-15)

**Built**
- 12 intermediate models (tables): calendar, cost history, customer de-duplication, enriched and orphan order lines, daily FX, enriched PO lines, daily inventory balance, daily true demand, ABC/XYZ, reorder inputs, RFM scores.
- 17 contract-enforced marts: `dim_date`, `dim_products`, `dim_customers`, `dim_suppliers`, `dim_warehouses`, `fct_order_lines` (incremental), `fct_orders`, `fct_purchase_order_lines`, `fct_inventory_daily` (incremental), `mart_inventory_health`, `mart_reorder_recommendations`, `mart_stockouts`, `mart_cycle_count_variance`, `mart_supplier_performance` (+ quarterly), `mart_sales_monthly`, `mart_customer_rfm`. Every mart column has a data type and description.
- Macros `safety_stock`, `round_up_to_case_pack`, `supplier_performance_metrics`; 5 singular tests; 3 more unit tests (reorder math, ABC boundaries, RFM segments); dashboard exposure; `overview.md` docs landing page.
- Generator: `cancel_reason` on orders, plus four realism fixes found by truth-recovery tests (see DECISIONS.md).
- `ci.yml` now runs on pull requests and pushes to main.

**Acceptance checks**
| Check | Result |
|---|---|
| Full `dbt build` on `small` | PASS=257, WARN=4 (the planted issues), ERROR=0 |
| Full `dbt build` on `medium` | PASS=257, WARN=4, ERROR=0 in 17s (2.9M inventory-day rows, 280k order lines) |
| `simulate-day && load && dbt build` processes only new and late-updated rows | `tests/test_dbt_incremental.py`: incremental run touched < 10% of order lines, late status changes applied, both incremental tables equal a full refresh |
| `dbt docs generate` | succeeds |
| Analysis recovers generator truth | `tests/test_dbt_marts.py`: supplier lead times within 10% on average, duplicate customers recovered exactly, A-class matches true demand weights, total demand within 15% of expected |
| sqlfluff, ruff, pytest | clean; 50 tests pass |

**What the small-scale marts show (synthetic; sanity check, not README findings yet)**
Dead stock, A-class SKUs below reorder point, A-class stockout days, supplier on-time range from 7% to 85%, quoted lead times optimistic by ~7 days on average. README numbers will be pulled from the medium-scale marts in Phase 5.

**Known issues**
- Source freshness still reports stale (simulated extraction time); catch-up mode planned for Phase 5/6.

**Next:** Phase 5, dashboard, docs site, README v1.

## Phase 5: Dashboard, docs site, README v1 (2026-10-15)

**Built**
- Repo pushed to https://github.com/orginalbusta/Wholesale-inventory-analytics (commit authors set to Harsh Arya with his GitHub noreply email before the first push). First CI run on Linux: green in 2m30s.
- `dashboard/`: Evidence (static edition) with 5 pages: Overview, Reorder (filters by category, supplier, ABC), Inventory health (ABC/XYZ heatmaps, dead stock, days of supply), Suppliers (reliability bubble chart, quoted vs. actual, quarterly trend, scorecard), Sales & customers (revenue by category with gem-show bands, channel and customer mix, RFM segments, At Risk call list). Disclaimer banner on every page.
- `deploy-pages.yml`: push + nightly; medium backfill, catch-up through yesterday, load, dbt build, freshness (non-blocking), docs, Evidence build, publish (`/` dashboard, `/dbt-docs/`).
- Generator `catch-up` mode (`make catch-up`) + byte-identical test vs. repeated simulate-day.
- README v1: business problem, 4 findings from the medium marts, Mermaid architecture, data-quality table, pipeline facts, run instructions, design decisions. No `<<FILL` placeholders.

**Checks so far**
| Check | Result |
|---|---|
| Dashboard `npm run build:strict` | passes; all 5 pages render with no query errors in the browser (20 charts) |
| Medium end-to-end (generate, load, dbt build) | 29s, PASS=257, WARN=4, ERROR=0 |
| README numbers | queried from the medium marts; duplicates (13) and test count (51) re-verified |
| Both sites live at public URLs | yes: dashboard https://orginalbusta.github.io/Wholesale-inventory-analytics/ (all 5 pages 200, data through 2026-10-14, no console errors) and dbt docs at `/dbt-docs/`; first deploy 2m19s |
| README links work, no `<<FILL` placeholders | yes: badges, live links and docs links all return 200; 0 placeholders |
| CI on push | green (2m12s) |

**Notes:** Pages source is "GitHub Actions". Minimum shippable version (Phases 0-5) is complete.

**Next:** Phase 6, orchestration (Dagster) and Docker.

## Phase 6: Orchestration (Dagster) and Docker (2026-10-15)

**Built**
- `orchestration/craftstones_dagster/definitions.py` (Dagster 1.13, dagster-dbt 0.29): `erp_extracts` (generator: backfill on first run, then catch-up through yesterday) → `raw_erp/<table>` (one asset per ERP table, a single dlt load) and `raw_fred/observations` → 48 dbt assets from the manifest (seeds, staging, intermediate, marts, snapshots; grouped by layer). dbt sources map onto the `raw_*` keys, so lineage runs from the generator to the marts with no stub assets.
- Asset checks: every dbt test (data tests and source tests), plus `source_freshness` on the two raw tables with freshness rules (runs `dbt source freshness`, reads `sources.json`). Two singular tests that reference several models got a `meta.dagster.ref` so they show up as checks instead of observations.
- `daily_pipeline_job` (all assets) and `daily_schedule` (06:00 America/Los_Angeles, off by default). In-process executor and a queued run coordinator with one run at a time, because DuckDB allows one writer (`orchestration/dagster.yaml`).
- Docker: `Dockerfile` (Python 3.12-slim, uv pinned to 0.9.26, `uv sync --frozen`, manifest built at image build time) and `docker-compose.yml` (webserver + daemon from one image, shared `dagster_home` volume, repo `data/` and `warehouse/` mounted), `.dockerignore`.
- CI: a `docker` job runs `docker compose up --build --wait`, `scripts/check_dagster_stack.py` (UI up, code location loaded, scheduler and run queue healthy), then executes `daily_pipeline_job` inside the container.
- `make dagster` keeps run history in `.dagster_home`; README run instructions mention `make dagster` and `docker compose up`.

**Acceptance checks**
| Check | Result |
|---|---|
| `make dagster` shows the full asset lineage | yes: generate → ingest → staging → snapshots / intermediate → marts, seeds → staging; 61 assets, 207 checks, no stub assets |
| Materializing all assets succeeds | yes, from the UI ("Materialize all") on the local warehouse: 61 materializations in 34s; checks: 203 pass, 4 warn (the planted issues, same as plain `dbt build`); freshness checks pass. Also covered by `tests/test_dagster.py` on a fresh temp warehouse |
| `docker compose up` brings up the UI | yes, in CI (Docker isn't installed locally; agreed with Harsh): webserver and daemon healthy, code location loaded, scheduler and run queue running; `daily_pipeline_job` inside the container: dbt PASS=257, WARN=4, ERROR=0, run succeeded. `docker` job ~2 min, in parallel with `build` |
| ruff, sqlfluff, pytest, dbt deprecations | clean; 57 tests pass; 0 dbt deprecation warnings |

**Known issues**
- The first CI run failed in the container at dbt seeds: the image's `dbt parse` used a relative project dir, and dbt reused that cached parse when Dagster ran dbt from inside `transform/`. Fixed by parsing with absolute paths in the Dockerfile (didn't reproduce on Windows, where the differing `DUCKDB_PATH` forces a full reparse).

**Next:** Phase 6.5, interactive dashboard (what-if reorder policy page + SKU drill-down pages).
