# 02: Architecture

## Data flow

```
 ┌──────────────────────┐     ┌──────────────────┐
 │ Synthetic ERP export │     │ FRED public API  │
 │ (generator/, seeded) │     │ (econ + FX data) │
 └─────────┬────────────┘     └────────┬─────────┘
           │ parquet files             │ JSON
           ▼                           ▼
     data/raw/erp/*.parquet     data/raw/fred/*.parquet
           │                           │
           └─────────── dlt ───────────┘
                         │  (append-only raw history + load_audit; FRED merge)
                         ▼
   ┌───────────────────────────────────────────────────────┐
   │ Warehouse: DuckDB (dev, CI) | Snowflake (optional)    │
   │  raw_erp.*  raw_fred.*                                │
   │      │                                                │
   │      ▼  dbt                                           │
   │  staging  →  intermediate  →  marts (core, inventory, │
   │  (views)     (ephemeral/      sales, suppliers)       │
   │               tables)         (tables, contracts)     │
   │  + seeds (gem show calendar, category map)            │
   │  + snapshots (product prices, customer terms: SCD2)   │
   └───────────────────────────┬───────────────────────────┘
                               │
            ┌──────────────────┼───────────────────┐
            ▼                  ▼                   ▼
   Evidence dashboard     dbt docs site      (later) forecasting /
   (static, GH Pages)     (GH Pages)         DS layer, LLM Q&A

 Orchestration: Dagster (generate → load → dbt assets), daily schedule
 CI: GitHub Actions (ruff, sqlfluff, pytest, dbt build on small data)
 Packaging: Docker + docker-compose for the Dagster stack
```

## Stack choices and why (put a version of this table in the README)

| Layer | Tool | Why this tool |
|---|---|---|
| Generation | Python, numpy, pandas/pyarrow, Faker | Full control over realistic distributions and planted data-quality issues; seeded and reproducible |
| Public data | FRED API (`fredapi` or plain `requests`) | Free, stable, real macro and FX series that plausibly affect a distributor |
| Ingestion | `dlt` (data load tool) | Declarative loads, schema inference/evolution, incremental merge, same code for DuckDB and Snowflake |
| Warehouse | DuckDB (default), Snowflake (optional target) | DuckDB is free and fast for dev and CI; Snowflake shows cloud-warehouse experience |
| Transformation | dbt Core (`dbt-duckdb`, `dbt-snowflake`) | Industry standard; tests, docs, lineage, snapshots, incrementals, contracts, unit tests |
| dbt packages | `dbt_utils`, `dbt_expectations`, `dbt_date` (optional) | Standard test and macro libraries |
| Orchestration | Dagster + `dagster-dbt` | Asset-based lineage that integrates cleanly with dbt; good local UI |
| BI | Evidence.dev | Dashboards as SQL + Markdown in git; builds a static site hostable free on GitHub Pages. (Fallback: Tableau Public if Harsh prefers. Decide in Phase 5.) |
| CI/CD | GitHub Actions | Lint, test, and build on every PR; deploy docs and dashboard on merge to main |
| Code quality | ruff, sqlfluff, pytest, pre-commit | Signals engineering hygiene |
| Packaging | Docker, docker-compose | One-command reproducible environment |

## Environments / dbt targets

| Target | Warehouse | Used by | Data scale |
|---|---|---|---|
| `dev` (default) | DuckDB file `warehouse/craftstones.duckdb` | Local development | `small` or `medium` |
| `ci` | DuckDB file in runner workspace | GitHub Actions | `small` |
| `snowflake` | Snowflake (key-pair auth via env vars) | Optional demo of cloud target | `medium` |

dbt models must be **warehouse-agnostic**: use `dbt_utils` / cross-database macros (`dbt.dateadd`, `dbt.datediff`, `dbt.date_trunc`, etc.) instead of DuckDB-only syntax. If a DuckDB-only function is unavoidable, wrap it in a macro with an adapter dispatch.

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
├── docs/                     # specs, PROGRESS.md, DECISIONS.md
├── generator/                # synthetic data generator (package)
│   ├── config.yaml           # scales, date range, planted-issue rates
│   ├── generate.py           # CLI entry point
│   └── ...                   # one module per entity (see 03_data_spec.md)
├── ingestion/                # dlt pipelines
│   ├── load_erp.py
│   └── load_fred.py
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
├── dashboard/                # Evidence project
├── tests/                    # pytest for generator + ingestion
├── data/                     # git-ignored; raw parquet + _truth/
└── warehouse/                # git-ignored; DuckDB files
```

## Incremental simulation (how "daily runs" work with synthetic data)

The generator has two modes:

1. **`backfill`**: generates the full history (default: 2023-10-01 → 2026-09-30) into `data/raw/erp/`.
2. **`simulate-day`**: reads the current generator state (`data/raw/_state.json`), generates **one more day** of orders, PO receipts, inventory movements, a few late status updates to existing orders, and occasional price/cost changes on products, then writes them as new parquet files and advances the state.

This makes incremental dbt models, `merge` loads in dlt, and dbt snapshots behave like they would against a live ERP. It's a good interview talking point. The Dagster daily schedule (off by default) materializes `erp_extracts` (catch-up: one simulated day per missing day through yesterday) → `raw_erp/*` + `raw_fred/observations` (dlt) → every dbt asset, with dbt tests and source freshness as asset checks.
