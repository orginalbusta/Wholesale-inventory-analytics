# Craftstones Data Platform: An Ideal-State Redesign

[![ci](https://github.com/orginalbusta/Wholesale-inventory-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/orginalbusta/Wholesale-inventory-analytics/actions/workflows/ci.yml)
[![deploy](https://github.com/orginalbusta/Wholesale-inventory-analytics/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/orginalbusta/Wholesale-inventory-analytics/actions/workflows/deploy-pages.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**[Live dashboard](https://orginalbusta.github.io/Wholesale-inventory-analytics/)** · **[What-if reorder policy](https://orginalbusta.github.io/Wholesale-inventory-analytics/what-if/)** · **[dbt docs & lineage](https://orginalbusta.github.io/Wholesale-inventory-analytics/dbt-docs/)**

From 2023 to 2026 I was the sole data analyst at **Craftstones USA**, a ~20-person wholesale stone distributor in San Diego, where I built the company's data function from scratch. This project answers the question I kept asking myself there: **if I could rebuild the data platform from zero with a modern stack, how would I do it?**

It centers on the decision that matters most to a distributor: **which products should we reorder, when, and how much, and where is cash tied up in dead stock?**

> **Please note**
> - **All data is synthetic.** It's generated to mimic a distributor's ERP (realistic demand, seasonality, gem-show spikes, supplier delays and deliberately messy records) and enriched with public FRED economic and exchange-rate data. No real Craftstones data, customers, suppliers, prices or volumes appear anywhere.
> - **This is my ideal-state design, not the system in use at Craftstones.** The architecture, tools and data model differ from what runs there. Numbers in this README describe the simulation, not the real business.

## At a glance

- **The pipeline:** a seeded Python generator produces messy ERP-style data (plus public FRED data) → **dlt** loads it raw → **dbt** builds tested staging, intermediate and contract-enforced mart layers → an **Evidence** dashboard and dbt docs on GitHub Pages, rebuilt every night. **Dagster** orchestrates it with end-to-end lineage.
- **The proof it works:** 214 dbt data tests and 8 unit tests, 67 pytest tests (including checks that the analysis recovers the generator's hidden truth), CI on every pull request, and every planted data-quality problem fixed or caught.
- **Interactive:** change the reorder policy on the [what-if page](https://orginalbusta.github.io/Wholesale-inventory-analytics/what-if/) and every SKU's safety stock, reorder point and order quantity is recalculated in your browser; every SKU has its own [drill-down page](https://orginalbusta.github.io/Wholesale-inventory-analytics/sku/).
- **Portable:** the same project runs on Snowflake, where all 18 marts came out identical to DuckDB.

[![What-if reorder policy page: raising the A-class service level to 99% and the cash it ties up](docs/images/what-if.png)](https://orginalbusta.github.io/Wholesale-inventory-analytics/what-if/)

*The what-if page with A-class SKUs moved to a 99% service level: 12 more SKUs to reorder now and $181k more cash in safety stock.*

## The business problem

For a distributor, inventory is the largest use of cash. The simulation starts the business on a deliberately naive purchasing policy (fixed "gut feel" reorder thresholds, suppliers' *quoted* lead times taken at face value, and optimistic bulk buys before every gem show) so the platform has real problems to find. That baseline produces three of them: **fast movers run out right before peak season**, **slow movers bought for shows sit unsold for months**, and **nobody measures which suppliers deliver late or short**. The baseline is a simulation device, not a description of how Craftstones actually purchased.

## Key findings

From the medium-scale simulation (3 years, 1,200 SKUs, 650 customers, 60 suppliers; generator seed 42, data through 2026-09-30). The live dashboard runs on the same simulation, extended one day every night, so its numbers drift slightly from these. All figures describe the synthetic business, not Craftstones.

1. **$158k of inventory, 9.2% of the $1.72M on hand, is dead stock**: 104 SKUs with no sale in 180+ days. Discontinued SKUs hold $113k (71%) of it. *Decision:* clear discontinued stock first (supplier returns, show liquidation), and stop including slow C-class SKUs in pre-show bulk buys. *Source:* `mart_inventory_health`.
2. **The products that matter most run out the most.** The 217 A-class SKUs, which make up 80% of revenue, logged 3,871 stockout days in the last 12 months (about 18 per SKU), leaving an estimated $2.47M of demand unfilled (an 88% unit fill rate). Right now 115 of the 210 active A-class SKUs are at or below the reorder point the platform calculates. *Decision:* replace fixed thresholds with reorder points that cover demand *and* lead-time variability, and reorder those 115 SKUs now. *Source:* `mart_stockouts`, `mart_reorder_recommendations`.
3. **Every supplier delivers slower than it quotes.** All 60 suppliers' actual lead times exceed their quotes, by 9.8 days on average, and on-time delivery ranges from 7% to 92% (median 44%). *Decision:* plan on measured lead times (the reorder logic already does) and put the least reliable suppliers on review. *Source:* `mart_supplier_performance`.
4. **Revenue is concentrated, and some of it is slipping away.** The top 20% of SKUs bring in 81% of revenue. 184 "Champion" customers account for 59% of the last 12 months' revenue, while 78 "At Risk" customers who used to order often, worth $2.4M over the last 12 months, have gone quiet. *Decision:* give sales reps the At Risk list as a call list. *Source:* `mart_customer_rfm`.
5. **Service level is a cash decision, and the dashboard prices it.** Raising every A-class SKU from today's 95-98% target to 99% adds $181k (+23%) of A-class safety stock and puts 12 more SKUs on today's reorder list; cutting C-class SKUs to 80% frees only $15k. *Decision:* set service levels per class deliberately, with the cost in view, instead of one blanket rule. *Source:* the what-if page, which recalculates `mart_reorder_recommendations` with the same formulas (a test checks they agree).

[![Dashboard overview: revenue and margin by month with gem-show bands, inventory value, dead stock and A-class SKUs to reorder](docs/images/dashboard-overview.png)](https://orginalbusta.github.io/Wholesale-inventory-analytics/)

*The dashboard overview on the same snapshot as the findings above (the live site keeps advancing nightly).*

## As-is vs. ideal-state

| | What I built at Craftstones | What this project designs |
|---|---|---|
| Storage | SQL databases + spreadsheets | Cloud-ready warehouse (DuckDB locally, Snowflake target) with raw / staging / marts layers |
| Pipelines | Python/SQL ETL scripts | dlt ingestion + dbt transformations, rebuilt from scratch nightly by GitHub Actions |
| Data quality | Manual checks | 214 automated dbt data tests, 8 dbt unit tests, enforced model contracts, source freshness |
| Reporting | Tableau dashboards | Version-controlled dashboard + public lineage docs, rebuilt on every merge |
| Forecasting & reorder | Regression forecast for inventory decisions | Reorder points from demand *and* supplier lead-time variability, ABC/XYZ service levels; a forecast plugs in as a swappable input |
| Change management | Single analyst, no review process | Git, CI on every pull request, reproducible builds |

## Architecture

```mermaid
flowchart LR
    gen["Synthetic ERP generator<br/>(Python, seeded)"] -->|parquet| dlt
    fred["FRED public data<br/>(FX, retail sales, sentiment)"] -->|API or CSV| dlt
    dlt["dlt<br/>append-only raw loads"] --> raw[("raw_erp / raw_fred")]
    subgraph wh ["Warehouse: DuckDB (default) · Snowflake (optional target)"]
        raw --> stg["dbt staging<br/>dedupe, clean, flag issues"]
        stg --> int["dbt intermediate<br/>demand, stock, costs, ABC/XYZ"]
        int --> marts["dbt marts<br/>contract-enforced"]
        stg --> snap["snapshots (SCD2)"]
    end
    marts --> evidence["Evidence dashboard"]
    marts --> docs["dbt docs + lineage"]
    evidence --> pages["GitHub Pages"]
    docs --> pages
    gha["GitHub Actions<br/>CI on every PR · nightly rebuild"] -.-> gen
```

| Layer | Tool |
|---|---|
| Data generation | Python (numpy, pandas, Faker), seeded and reproducible |
| Public data | FRED (FX rates, retail sales, consumer sentiment) |
| Ingestion | dlt |
| Warehouse | DuckDB (default) · Snowflake (optional target) |
| Transformation | dbt Core: staging/intermediate/marts, snapshots (SCD2), incremental models, contracts, unit tests |
| Orchestration | Dagster (+ dagster-dbt): end-to-end asset lineage, dbt tests as asset checks, daily schedule; Docker Compose |
| BI | Evidence (static site on GitHub Pages), with in-browser what-if analysis |
| CI/CD | GitHub Actions: ruff, sqlfluff, pytest, dbt build; nightly rebuild and deploy |

## Data quality: what the pipeline handles

The synthetic ERP export contains ten deliberately planted problems that real distributor data has. Each one is either fixed in staging or caught by a dbt test, and a pytest checks every planted record against the generator's ground truth.

| Problem | How it's handled |
|---|---|
| Duplicate customers ("Rock & Gem Shop" vs. "Rock and Gem Shop LLC") | Flagged by a warn test; merged in `int_customers__deduplicated` (name and email match rules). All 13 planted duplicates recovered exactly |
| Inconsistent category labels (`POLISHED`, `Polished  Stones `) | Normalized and mapped via a seed in `stg_erp__products` |
| SKU code variants (`amt-pls-0042`, `AMTPLS0042`) | `normalize_sku()` macro, unit-tested |
| Re-extracted duplicate rows and late status updates | Raw keeps every extract; staging keeps the latest version; incremental facts re-process a 7-day lookback |
| Returns keyed as negative quantities | Flagged as return lines in staging; revenue and COGS reversed |
| Null or malformed emails | Flagged (`is_email_valid`) with a warn-level regex test |
| Mixed date formats (`2025-03-04` vs `03/04/2025`) | `parse_mixed_date()` macro, unit-tested |
| Order lines with SKUs that don't exist | Caught by a warn-level relationships test; quarantined in `int_order_lines__orphans` |
| Cycle counts that find large losses | Flagged by a variance test; reported in `mart_cycle_count_variance` |

## Pipeline facts

- **Volume (medium scale):** 671,541 raw rows loaded; 279,715 order lines; 2.9M SKU-warehouse-day inventory rows.
- **dbt project:** 42 models (12 staging, 12 intermediate, 18 marts), 2 snapshots, 5 seeds, 214 data tests, 8 unit tests; every mart has an enforced contract.
- **Build time (medium, on a laptop):** generate 8s, load 11s (mostly fetching FRED), `dbt build` 16s.
- **CI:** on every PR and push: lint (PRs lint only the SQL they change), a full pipeline build on small data, 67 pytest tests (including truth-recovery checks, a full Dagster run, and a check that the dashboard's what-if page reproduces the reorder mart), and a Docker check of the Dagster stack, in about 3 minutes. A broken model fails with a summary table naming the model and dbt's error.

## Run it yourself

Needs Python 3.12 (installed automatically by [uv](https://docs.astral.sh/uv/)), Node.js 20+ for the dashboard, and `make` (no `make` on Windows? each target is a one-line command in the [Makefile](Makefile); run it directly).

```bash
git clone https://github.com/orginalbusta/Wholesale-inventory-analytics.git
cd Wholesale-inventory-analytics
make setup           # Python deps (uv) and dbt packages
make all             # generate synthetic data → load → dbt build (DuckDB)
make dashboard       # local dashboard
make simulate-day    # add one day of new data, then `make load dbt-build` to see incrementals in action
make dagster         # Dagster UI at localhost:3000: end-to-end lineage; "Materialize all" runs the pipeline
```

Or run the orchestration stack in Docker (Dagster webserver + daemon, no local Python needed): `docker compose up`, then open http://localhost:3000.

`make generate SCALE=medium` builds the larger dataset the findings above come from. A free `FRED_API_KEY` in `.env` is optional: without it, FRED's public CSV download is used, and the build never depends on FRED being reachable.

### Where to look

| Folder | What's there |
|---|---|
| [`generator/`](generator/) | Seeded simulation of the business: demand, purchasing, stock ledger, planted data-quality issues, hidden ground truth |
| [`ingestion/`](ingestion/) | dlt loaders for the ERP extracts and FRED (DuckDB or Snowflake) |
| [`transform/`](transform/) | The dbt project: sources, staging, intermediate, marts, snapshots, macros, tests |
| [`orchestration/`](orchestration/) | Dagster code location (assets, checks, schedule) |
| [`dashboard/`](dashboard/) | Evidence pages, including the what-if and per-SKU pages |
| [`tests/`](tests/) | pytest: generator, loads, dbt builds, truth recovery, Dagster, dashboard parity |
| [`docs/`](docs/) | Specs, the [decision log](docs/DECISIONS.md) and the [progress log](docs/PROGRESS.md) |

## Running on Snowflake

The same dlt loads and dbt project also run on Snowflake (`--target snowflake`, key-pair auth); the
public site and CI stay on DuckDB, which is free. Setup and commands: [`snowflake/README.md`](snowflake/README.md).

On the medium dataset with an X-Small warehouse: the full `dbt build` (272 nodes) took **57 seconds**
with the same results as DuckDB (PASS 267, WARN 4, ERROR 0), and all **18 marts were identical**
across the two warehouses (row counts and the sum of every numeric column), after a full build
and again after an incremental run. The whole session used at most about **0.2 credits**
(about 10 minutes of warehouse time; the warehouse suspends after 60 idle seconds and has a hard
credit cap).

## Design decisions and trade-offs

Every decision and deviation from the original plan is logged, with reasoning, in [`docs/DECISIONS.md`](docs/DECISIONS.md). The main ones:

- **DuckDB for the public site, Snowflake as a showcase target.** The site never queries a warehouse, so it stays free to host; the same dbt code targets both.
- **An append-only raw layer.** Raw tables keep every extract, so duplicates and late updates are resolved (and tested) in dbt instead of disappearing inside the loader.
- **Cost as of the order date** comes from the ERP's price-change log, so margins are right for the whole history, not only after the first snapshot.
- **True demand includes stockouts.** Reorder points (and any future forecast) are built on what customers asked for, not on censored sales.
- **A deterministic simulation.** Same seed, same bytes. A "simulate one more day" mode exercises incremental models, and tests check that the analysis recovers the generator's hidden truth.
- **Analysis in the browser, checked against dbt.** The what-if page re-runs the reorder formulas client-side on a static site (no server to pay for), and a test fails CI if its numbers ever drift from the dbt mart.
- **Orchestration as assets, not scripts.** Dagster models every raw table and dbt model as an asset, so lineage runs from the generator to the marts and dbt tests show up as asset checks.

## If I had more time

SKU-level demand forecasting to replace historical-average reorder points (the reorder mart is already built to swap in forecasts), a pricing experiment analysis, and a natural-language "ask the data" interface over the documented marts. See [`docs/06_future_ds_layer.md`](docs/06_future_ds_layer.md).

## License

[MIT](LICENSE). All data in this repository is synthetic.
