# 05: Roadmap (build phase by phase)

Each phase ends with: acceptance checks pass → update `docs/PROGRESS.md` → commit → stop and report to Harsh.

**Minimum shippable version = Phases 0–5.** That is the version worth linking on a resume. Phases 6–9 make it stronger. Target: Phases 0–5 in about 2 weeks of part-time work.

---

## Phase 0: Environment and skeleton
- `uv` project set up from `pyproject.toml`; verify and tighten dependency ranges to current releases.
- `make setup` works; `dbt deps` installs packages; `dbt debug --target dev` passes.
- pre-commit installed with ruff + sqlfluff hooks.
- Create `docs/PROGRESS.md` and `docs/DECISIONS.md`.

**Accept when:** `make setup && make lint` succeed on a clean clone; `uv run dbt debug --project-dir transform --profiles-dir transform` passes.

## Phase 1: Synthetic data generator
- Implement `generator/` per `03_data_spec.md`: reference dims, demand simulation, naive purchasing, day-by-day inventory ledger, cycle counts, planted issues, `_truth/` outputs, `backfill` and `simulate-day` modes.
- CLI: `uv run python -m generator.generate --scale small --mode backfill`.
- pytest: determinism (same seed → same hash), volumes within ±25% of targets, ledger never negative in truth, planted issues present at configured rates, Pareto check (top 20% SKUs ≈ 75–80% revenue), seasonality visible (Nov jewelry > Jul jewelry), at least some stockouts and some dead stock exist.

**Accept when:** `make generate SCALE=small` runs in < 60s, `make test` passes, and a short summary script prints sane stats (rows per table, revenue by month, top categories).

## Phase 2: Ingestion with dlt
- `ingestion/load_erp.py`: load each `data/raw/erp/<table>/` into `raw_erp.<table>`. Merge on PK for mutable tables (orders, POs, products, customers); append for ledgers (movements, counts). Destination from env (`duckdb` default, `snowflake` optional).
- `ingestion/load_fred.py`: fetch the series in `03_data_spec.md` into `raw_fred.observations`; incremental on date; skip gracefully without `FRED_API_KEY`.
- Running `load` twice must not duplicate rows.

**Accept when:** `make load` populates DuckDB; row counts match parquet; re-running is idempotent; `make simulate-day && make load` adds only the new day.

## Phase 3: dbt sources, seeds, staging, snapshots
- Sources with freshness; seeds; all staging models; macros `normalize_sku`, `parse_mixed_date`, `generate_schema_name`; snapshots.
- Tests on staging PKs and planted issues; unit test for `normalize_sku`.

**Accept when:** `dbt build --select staging+ seeds snapshots` passes (warn-severity tests may warn); every planted issue is either fixed in staging or caught by a test (cross-check against `data/_truth/planted_issues.parquet` in a pytest).

## Phase 4: Intermediate and marts
- All intermediate and mart models from `04_dbt_spec.md`, contracts on marts, singular tests, unit tests for reorder math, ABC boundaries, and RFM.
- Incremental `fct_order_lines` and `fct_inventory_daily` verified with `simulate-day`.
- Sanity-check: the analysis should roughly recover generator truth (e.g., estimated supplier lead times close to `_truth/` means). Add a pytest for this.

- Enable `ci.yml` on `pull_request` and `push` to main (it is manual-only until now).

**Accept when:** full `dbt build` passes on `small` and `medium`; `make simulate-day && make load && make dbt-build` succeeds and only processes new and late-updated rows; `dbt docs generate` succeeds.

## Phase 5: Dashboard, docs site, README v1 (MINIMUM SHIPPABLE)
- Evidence project in `dashboard/` reading the DuckDB marts. Every page shows a short banner: "Synthetic data · ideal-state design, not the production system at Craftstones." Pages:
  1. **Overview**: revenue/margin trend, inventory value, dead-stock value, A-items below reorder point
  2. **Reorder**: sortable table from `mart_reorder_recommendations` with filters (category, supplier, ABC)
  3. **Inventory health**: ABC/XYZ matrix, dead stock list, days of supply distribution
  4. **Suppliers**: on-time vs. lead-time variability scatter, quoted vs. actual
  5. **Sales and customers**: monthly trend by category with show windows shaded, RFM segments
- GitHub Actions workflow `deploy-pages.yml` (finish the Evidence build step, then add the push trigger): on push to main → generate `medium` data → load → dbt build → build Evidence site + `dbt docs generate` → publish both to GitHub Pages (`/` dashboard, `/dbt-docs/` docs).
- README v1: real findings from the data (no invented numbers), architecture diagram (Mermaid), stack table, how to run.
- **Nightly refresh:** a scheduled workflow (cron) that restores the previous run's generator state, runs `simulate-day → load → dbt build`, and redeploys, so the live site shows an advancing "data as of" date. Free on a public repo. (Agreed with Harsh 2026-10-14; see DECISIONS.md.)

**Accept when:** both sites are live at public URLs; README links work; README contains no `<<FILL` placeholders.

> Decision point for Harsh: Evidence vs. Tableau Public. Evidence is code-reviewable and auto-deploys; Tableau Public reuses an existing resume skill. Default to Evidence unless he says otherwise.

## Phase 6: Orchestration (Dagster) and Docker
- `orchestration/craftstones_dagster/`: assets for `simulate_day` → `erp_load` / `fred_load` → dbt assets (via `dagster-dbt`, from the dbt manifest) → source freshness check. Daily schedule (off by default), asset checks wired from dbt tests.
- `Dockerfile` and `docker-compose.yml` that run the Dagster webserver + daemon with the project mounted.

**Accept when:** `make dagster` shows the full asset lineage; materializing all assets succeeds; `docker compose up` brings up the UI.

## Phase 6.5: Interactive dashboard (what-if reorder policy + SKU drill-downs)
Added 2026-10-15 at Harsh's request (see DECISIONS.md). Numbered 6.5 so the later phases keep their numbers. Everything runs in the visitor's browser (Evidence's static build queries an in-browser DuckDB), so the site stays free and serverless.

- **What-if reorder policy page** (`dashboard/pages/what-if.md`). Inputs:
  - **Service level** (e.g. 90 / 95 / 97.5 / 99 / 99.5%), applied to all SKUs or per ABC class. z comes from a seeded lookup table, not an in-browser inverse-normal function, so the page and dbt use the same numbers.
  - **Lead-time buffer** (+0 to +30 days added to `lead_time_mean_days`).
  - **Review period** (e.g. 7 to 60 days, replacing the `review_period_days` var).
- The page recomputes the `04_dbt_spec.md` reorder formulas per SKU from the mart's exposed inputs (`demand_mean_daily`, `demand_std_daily`, `lead_time_mean_days`, `lead_time_std_days`, on-hand, on-order, case pack, unit cost): safety stock, reorder point, reorder-now flag, suggested qty, rounded up to the case pack.
- Outputs compare the current policy with the scenario: SKUs to reorder now, total order value, safety-stock value (cash tied up), plus a per-SKU table with the deltas. A short note explains the trade-off: a higher service level means fewer stockouts but more cash in stock.
- If the mart is missing an input the page needs, expose it in `mart_reorder_recommendations` (contract + docs updated). The page never re-derives business logic from staging.
- **SKU drill-down pages** (`dashboard/pages/sku/[sku].md`, one templated page per SKU): stock on hand over time with the reorder point and safety stock drawn in, weekly demand, stockout days, open and recent POs (quoted vs. actual lead time), primary supplier's scorecard, ABC/XYZ class, and the current recommendation. SKU cells in the Reorder, Inventory health and What-if tables link here.
- Keep the build within the CI and deploy time budgets: limit the time series on drill-down pages (e.g. trailing 12 months) so the static build doesn't balloon at `medium` scale.

**Accept when:** at the default inputs (current seed service levels, +0 buffer, current review period), the what-if page reproduces `mart_reorder_recommendations` exactly (a pytest or a dbt test compares the page's SQL against the mart); moving each input changes the outputs in the expected direction; every active SKU has a drill-down page that builds with no query errors; `npm run build:strict` passes; deploy time stays under ~5 minutes.

## Phase 7: CI hardening
- `ci.yml` on PR: ruff, sqlfluff (lint changed SQL), pytest, generate `small` → load → `dbt build --target ci`. Cache uv and dbt packages. Target < 6 min.
- Optional: slim CI (`state:modified+` against main's manifest artifact).

**Accept when:** a PR with a deliberately broken model fails CI with a readable error; a clean PR passes.

## Phase 8: Snowflake target (optional, needs credentials)
- Harsh starts the 30-day Snowflake trial right before this phase so the credits aren't wasted. Set auto-suspend (60s) on the warehouse and a resource monitor with a hard credit cap.
- The public site keeps building from DuckDB; Snowflake results go into the README (screenshots, build time, credits used).
- Configure `snowflake` target with key-pair auth via env vars; dlt Snowflake destination.
- Run `medium` end-to-end on Snowflake; capture a screenshot or two for the README; note warehouse size and credit usage.
- Confirm cross-database macros work on both adapters.

**Accept when:** `dbt build --target snowflake` passes. Document setup in README "Running on Snowflake".

## Phase 9: Polish for hiring managers
- README final pass: 3–5 findings written as business decisions ("Moving 14 A-class SKUs to forecast-driven reorder points would have avoided ~N stockout days"), each with the number and the mart it came from.
- Add a short "Design decisions and trade-offs" section (DuckDB vs. Snowflake, why dlt, incremental strategy, SCD2 for cost, how planted DQ issues are handled).
- Add an "If I had more time" section, pointing to the DS layer.
- Repo hygiene: badges (CI status), license (MIT), clean commit history, no secrets, no large files.

**Accept when:** someone unfamiliar with the project understands the business problem, the architecture, and the main findings within 2 minutes of opening the README.

---

## Later (do not start without Harsh's go-ahead)
See `06_future_ds_layer.md`.
