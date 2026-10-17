# 02: Architecture

*Kept current with the build. For a one-page version, see [HOW_IT_WORKS.md](HOW_IT_WORKS.md).*

## Data flow

```
 ┌──────────────────────┐     ┌──────────────────────┐
 │ Synthetic ERP export │     │ FRED public data     │
 │ (generator/, seeded) │     │ (API or public CSV)  │
 └─────────┬────────────┘     └──────────┬───────────┘
           │ parquet files               │ fetched directly
           ▼                             │
     data/raw/erp/*.parquet              │
           │                             │
           └──────────── dlt ────────────┘
                         │  (append-only raw history + load_audit; FRED merge)
                         ▼
   ┌───────────────────────────────────────────────────────┐
   │ Warehouse: DuckDB (dev, CI) | Snowflake (optional)    │
   │  raw_erp.*  raw_fred.*                                │
   │      │                                                │
   │      ▼  dbt                                           │
   │  staging  →  intermediate  →  marts (core, inventory, │
   │  (views)     (tables)         sales, suppliers)       │
   │                               (tables, contracts)     │
   │  + seeds (show calendar, categories, FX, service lvl) │
   │  + snapshots (product prices, customer terms: SCD2)   │
   └───────────────────────────┬───────────────────────────┘
                               │
            ┌──────────────────┼───────────────────┐
            ▼                  ▼                   ▼
   Evidence dashboard     dbt docs site      (later) forecasting /
   (static, GH Pages,     (GH Pages)         DS layer, LLM Q&A
    in-browser DuckDB)

 Orchestration: Dagster (generate → load → dbt assets, dbt tests as asset checks), daily schedule
 CI: GitHub Actions on every PR (lint, small pipeline + dbt build, pytest, Docker check)
 Deploy: GitHub Actions on push and nightly (rebuild from scratch, publish to GitHub Pages)
 Packaging: Docker + docker-compose for the Dagster stack
```

## Stack choices and why

| Layer | Tool | Why this tool |
|---|---|---|
| Generation | Python, numpy, pandas/pyarrow, Faker | Full control over realistic distributions and planted data-quality issues; seeded and reproducible |
| Public data | FRED (official API with a key, public CSV without; `requests`) | Free, stable, real macro and FX series that plausibly affect a distributor |
| Ingestion | `dlt` (data load tool) | Declarative loads, schema inference, append-only raw history (FRED merged on key), same code for DuckDB and Snowflake |
| Warehouse | DuckDB (default), Snowflake (optional target) | DuckDB is free and fast for dev and CI; Snowflake shows cloud-warehouse experience |
| Transformation | dbt Core (`dbt-duckdb`, `dbt-snowflake`) | Industry standard; tests, docs, lineage, snapshots, incrementals, contracts, unit tests |
| dbt packages | `dbt_utils`, `dbt_expectations` (+ `dbt_date`, its dependency) | Standard test and macro libraries |
| Orchestration | Dagster + `dagster-dbt` | Asset-based lineage that integrates cleanly with dbt; good local UI |
| BI | Evidence.dev (open-source static edition) | Dashboards as SQL + Markdown in git; builds a static site hostable free on GitHub Pages; queries run in the browser, which makes the what-if page possible |
| CI/CD | GitHub Actions | Lint, test, and build on every PR; deploy docs and dashboard on merge to main |
| Code quality | ruff, sqlfluff, pytest, pre-commit | Signals engineering hygiene |
| Packaging | Docker, docker-compose | One-command reproducible environment |

## Environments / dbt targets

| Target | Warehouse | Used by | Data scale |
|---|---|---|---|
| `dev` (default) | DuckDB file `warehouse/craftstones.duckdb` | Local development | `small` or `medium` |
| `ci` | DuckDB file in runner workspace | GitHub Actions | `small` |
| `snowflake` | Snowflake (key-pair auth via env vars) | Optional demo of cloud target | `medium` |

dbt models are **warehouse-agnostic**: day arithmetic on dates is plain SQL that DuckDB and Snowflake treat the same (`date - date`, `date - 365`), `dbt.dateadd` is used for timestamps, and the few engine-specific functions (regex) sit in adapter-dispatched macros (`macros/cross_db.sql`). Verified in Phase 8: all 18 marts are identical on both warehouses.

## Schemas in the warehouse

- `raw_erp`, `raw_fred`: written by dlt only. Never modified by dbt.
- `staging`, `intermediate`, `marts`, `snapshots`, `seeds`: written by dbt (configure via `+schema` with a `generate_schema_name` override so names are clean, not `dev_staging`).

## Repo layout

```
wholesale-inventory-analytics/
├── README.md                 # the case study (public face of the project)
├── Makefile
├── pyproject.toml            # uv-managed Python deps
├── .env.example
├── .sqlfluff / .sqlfluffignore
├── .pre-commit-config.yaml
├── Dockerfile / docker-compose.yml
├── .github/workflows/        # ci.yml, deploy-pages.yml
├── LICENSE                   # MIT
├── docs/                     # HOW_IT_WORKS.md, specs, PROGRESS.md, DECISIONS.md, images/
├── generator/                # synthetic data generator (package)
│   ├── config.yaml           # scales, date range, planted-issue rates
│   ├── generate.py           # CLI entry point
│   └── ...                   # one module per entity (see 03_data_spec.md)
├── ingestion/                # dlt pipelines
│   ├── load_erp.py
│   ├── load_fred.py
│   └── destinations.py       # DuckDB or Snowflake, from WAREHOUSE
├── transform/                # dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml          # uses env vars; safe to commit
│   ├── packages.yml
│   ├── models/{staging,intermediate,marts}/
│   ├── snapshots/
│   ├── seeds/
│   ├── macros/
│   ├── tests/                # singular tests
│   └── analyses/
├── orchestration/            # Dagster code location
│   └── craftstones_dagster/
├── dashboard/                # Evidence project (pages/, sources/)
├── scripts/                  # FX seed builder, CI/deploy helpers, warehouse comparison
├── snowflake/                # one-time setup/teardown SQL + walkthrough
├── tests/                    # pytest: generator, loads, dbt, truth recovery, Dagster, dashboard
├── data/                     # git-ignored; raw parquet + _truth/
└── warehouse/                # git-ignored; DuckDB files
```

## Incremental simulation (how "daily runs" work with synthetic data)

The generator has two modes:

1. **`backfill`**: generates the full history (default: 2023-10-01 → 2026-09-30) into `data/raw/erp/`.
2. **`simulate-day`**: reads the current generator state (`data/raw/_state.json`), generates **one more day** of orders, PO receipts, inventory movements, a few late status updates to existing orders, and occasional price/cost changes on products, then writes them as new parquet files and advances the state.

A third mode, **`catch-up`**, writes one day-only extract for every missing day through a given date (the nightly deploy uses it to stay current). These make incremental dbt models, idempotent dlt loads and dbt snapshots behave like they would against a live ERP. The Dagster daily schedule (off by default) materializes `erp_extracts` (catch-up: one simulated day per missing day through yesterday) → `raw_erp/*` + `raw_fred/observations` (dlt) → every dbt asset, with dbt tests and source freshness as asset checks.
