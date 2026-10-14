# Craftstones Data Platform: An Ideal-State Redesign

<!-- Badges (Phase 7): CI status, dbt docs link, dashboard link -->

**Live dashboard:** <<FILL: GitHub Pages URL>> · **dbt docs & lineage:** <<FILL: GitHub Pages URL>>/dbt-docs/

From 2023 to 2026 I was the sole data analyst at **Craftstones USA**, a ~20-person wholesale stone distributor in San Diego, where I built the company's data function from scratch. This project answers the question I kept asking myself there: **if I could rebuild the data platform from zero with a modern stack, how would I do it?**

It centers on the decision that matters most to a distributor: **which products should we reorder, when, and how much, and where is cash tied up in dead stock?**

> **Please note**
> - **All data is synthetic.** It's generated to mimic a distributor's ERP (realistic demand, seasonality, gem-show spikes, supplier delays and deliberately messy records) and enriched with public FRED economic and exchange-rate data. No real Craftstones data, customers, suppliers, prices or volumes appear anywhere.
> - **This is my ideal-state design, not the system in use at Craftstones.** The architecture, tools and data model differ from what runs there. Numbers in this README describe the simulation, not the real business.

## As-is vs. ideal-state

| | What I built at Craftstones | What this project designs |
|---|---|---|
| Storage | SQL databases + spreadsheets | Cloud-ready warehouse (DuckDB locally, Snowflake target) with raw / staging / marts layers |
| Pipelines | Python/SQL ETL scripts | dlt ingestion + dbt transformations, orchestrated daily by Dagster |
| Data quality | Manual checks | <<FILL: # >> automated dbt tests, model contracts, source freshness |
| Reporting | Tableau dashboards | Version-controlled dashboards + public lineage docs, rebuilt on every merge |
| Forecasting & reorder | Regression forecast for inventory decisions | Reorder points from demand *and* supplier lead-time variability, ABC/XYZ service levels; forecast plugs in as a swappable input |
| Change management | Single analyst, no review process | Git, CI on every pull request, reproducible builds |

<<Harsh: confirm the left column matches what you actually did; keep it modest and accurate.>>

## The business problem

<<FILL in Phase 5: 3–4 sentences from docs/01_business_context.md: stockouts on fast movers before peak season, dead stock from overbuying for gem shows, unmeasured supplier reliability. State that the comparison baseline is a simulated purchasing policy.>>

## Key findings

<<FILL in Phase 5/9 from real mart outputs. Format: finding → number → decision it supports → source mart. 3 to 5 findings. Never invent numbers. Phrase as results in the simulation ("in the simulated data…"), never as Craftstones' real results.>>

1. <<FILL>>
2. <<FILL>>
3. <<FILL>>

## Architecture

<<FILL in Phase 5: Mermaid diagram of generator/FRED → dlt → DuckDB/Snowflake → dbt (staging → intermediate → marts) → Evidence + dbt docs, orchestrated by Dagster, checked by GitHub Actions.>>

| Layer | Tool |
|---|---|
| Data generation | Python (numpy, pandas, Faker), seeded and reproducible |
| Public data | FRED API (FX rates, retail sales, consumer sentiment) |
| Ingestion | dlt |
| Warehouse | DuckDB (default) · Snowflake (optional target) |
| Transformation | dbt Core: staging/intermediate/marts, snapshots (SCD2), incremental models, contracts, unit tests |
| Orchestration | Dagster |
| BI | Evidence.dev (static site on GitHub Pages) |
| CI/CD | GitHub Actions: ruff, sqlfluff, pytest, dbt build |

## Data quality: what the pipeline handles

The synthetic ERP export contains deliberately planted problems that real distributor data has: duplicate customers, inconsistent category labels, SKU code variants, re-extracted duplicate rows, late-arriving status updates, mixed date formats, returns encoded as negative quantities, and orphan records. <<FILL: how each is handled, and that tests catch them; link to the relevant models.>>

## Pipeline facts

<<FILL: rows processed, # dbt models, # tests, build time on DuckDB (small/medium), on Snowflake if run.>>

## Run it yourself

```bash
git clone <<FILL repo URL>>
cd wholesale-inventory-analytics
make setup           # installs Python deps (uv) and dbt packages
make all             # generate synthetic data → load → dbt build (DuckDB)
make dashboard       # local dashboard
make simulate-day    # add one day of new data, then `make load dbt-build` to see incrementals in action
```

Optional: copy `.env.example` to `.env` and add a free `FRED_API_KEY` for live FX and macro data (the build falls back to static seed rates without it).

## Design decisions and trade-offs

<<FILL in Phase 9 from docs/DECISIONS.md.>>

## If I had more time

Demand forecasting at SKU level to replace historical-average reorder points (the reorder mart is already built to swap in forecasts), a pricing experiment analysis, and a natural-language "ask the data" interface over the documented marts.
