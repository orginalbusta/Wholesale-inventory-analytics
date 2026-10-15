# CLAUDE.md: Project brief for Claude Code

You are helping Harsh Arya build a **portfolio data engineering project** that will be linked from his resume and reviewed by hiring managers for **Analytics Engineer / Data Engineer** roles. Quality, clarity, and finished-ness matter more than breadth.

## What we're building (one paragraph)

An **ideal-state redesign** of the data platform for **Craftstones USA**, the ~20-person San Diego wholesale stone distributor where Harsh was the sole data analyst (2023 to 2026). The project answers: *"If I could rebuild Craftstones' data system from scratch with a modern stack, here's how I'd do it."* The data is **synthetic**, and the architecture is Harsh's proposed design, **not** the system actually in use at Craftstones. A Python generator produces realistic, deliberately messy ERP-style data (orders, purchase orders, inventory movements, suppliers, customers), enriched with public economic/FX data from FRED. Data is loaded raw into a warehouse with `dlt`, transformed with **dbt** into tested staging → intermediate → mart layers, orchestrated with **Dagster**, checked in **GitHub Actions CI**, and surfaced in a **public dashboard** plus hosted **dbt docs**. The business question: *which SKUs should we reorder, when, and how much, and where is cash tied up in dead stock?*

## Read these first, in order

1. `docs/01_business_context.md`: the company, stakeholders, decisions the platform supports
2. `docs/02_architecture.md`: stack, layers, environments, repo layout
3. `docs/03_data_spec.md`: **the source of truth** for synthetic tables, columns, distributions, and planted data-quality issues
4. `docs/04_dbt_spec.md`: every dbt model, test, snapshot, and mart definition
5. `docs/05_roadmap.md`: phased build plan with acceptance criteria. **Work phase by phase.**
6. `docs/06_future_ds_layer.md`: later work. Do NOT build it now, but don't design anything that blocks it.

## Working rules

- **Work one phase at a time** from `docs/05_roadmap.md`. At the end of each phase: run the phase's acceptance checks, update `docs/PROGRESS.md`, and make a commit. Then stop and summarize for Harsh before starting the next phase unless he said to continue.
- **The spec docs are the plan, not scripture.** If something in them is wrong, outdated (e.g., a package version or API changed), or unworkable, fix it, note the deviation in `docs/DECISIONS.md` (date, what, why), and keep going. Ask Harsh only for decisions that change scope or cost money.
- **Zero cost by default.** Local dev and CI run on **DuckDB**. Snowflake is an optional second target (`--target snowflake`) used only when Harsh has credentials configured. Never require a paid service for the default path.
- **Reproducible.** The generator is seeded; `make all` from a clean clone must rebuild everything. CI uses the `small` scale.
- **dbt version:** use dbt Core v1 (`dbt-core` + `dbt-duckdb` from pip), not the newer dbt v2 default install. Keep the project v2-compatible: treat every dbt deprecation warning as a bug. See `docs/DECISIONS.md`.
- **Verify package versions** against PyPI / hub.getdbt.com before pinning. Versions in this scaffold are loose starting ranges, not verified pins.
- **Keep the default build fast.** `small` scale should run end-to-end (generate → load → dbt build) in under ~3 minutes locally.
- **Prefer boring, legible code.** A hiring manager will skim it. Clear names, docstrings on modules, no clever metaprogramming.

## Honesty and framing (important)

- **Using the Craftstones name is intended**, with two disclaimers that must stay prominent at the top of the README and the dashboard: (1) **all data is synthetic**, and (2) **this is an ideal-state design, not the system in production at Craftstones.** Never imply this platform ran at Craftstones, and never present synthetic numbers as Craftstones' real results.
- **No real or confidential company data, ever:** no real customer or supplier names, prices, costs, margins, volumes, or revenue. All of those are generated. Don't use Craftstones' logo or brand assets.
- The business context in `docs/01_business_context.md` describes the company's situation at a high level. Some details are planning assumptions marked for Harsh to confirm; don't add new specific claims about the real company.
- The README's **"As-is vs. ideal-state"** section compares the setup Harsh actually built (from his resume) with this design. That comparison is a core part of the story, so keep it accurate and modest.
- Findings in the README must come from actually running the pipeline. Never write invented numbers. Use placeholders like `<<FILL FROM mart_inventory_health>>` until the numbers exist.

## Conventions

- **Python** ≥ 3.12 (pinned to 3.12 in `.python-version`), managed with `uv` (`uv sync`, `uv run ...`). Lint/format with `ruff`. Tests with `pytest`.
- **SQL**: lowercase keywords, trailing commas, CTE-first style, lint with `sqlfluff` (config in `.sqlfluff`, dialect duckdb).
- **dbt naming**: `stg_<source>__<entity>`, `int_<verb/entity>`, `dim_*`, `fct_*`, `mart_*`. One `_<dir>__models.yml` per directory. Every model has a description; every primary key has `unique` + `not_null`.
- **Commits**: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `ci:`).
- **Secrets** only via `.env` (git-ignored); `.env.example` documents them.

## Key commands (keep the Makefile in sync with this list)

```
make setup          # uv sync + dbt deps
make generate       # synthetic data, SCALE=small|medium (default small)
make summary        # print sanity stats for the generated data
make load           # dlt: data/raw -> warehouse raw schemas
make dbt-build      # dbt build, incremental (models + tests + snapshots + seeds)
make all            # generate + load + dbt build --full-refresh (rebuild from scratch)
make simulate-day   # append one day of new data (exercises incrementals + snapshots)
make catch-up       # simulate every missing day through yesterday (used by the nightly deploy)
make docs           # dbt docs generate
make lint           # ruff + sqlfluff
make test           # pytest
make dagster        # dagster dev UI
make dashboard      # run the Evidence dashboard locally
```

## Definition of done (whole project)

- A clean clone can run `make setup && make all` and get a fully built, fully tested DuckDB warehouse.
- CI is green on every PR: lint, pytest, `dbt build` on `small` data.
- dbt docs (with lineage graph) and the dashboard are publicly hosted on GitHub Pages.
- README reads like a business case study with real findings from the data, an architecture diagram, and run instructions.
- `docs/PROGRESS.md` and `docs/DECISIONS.md` are current.
