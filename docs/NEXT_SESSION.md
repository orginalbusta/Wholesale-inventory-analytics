# Next session: pick up here

*Updated 2026-10-15 at the end of Phase 6. Read this first, then `CLAUDE.md`, `docs/PROGRESS.md` and `docs/DECISIONS.md` (newest entries at the top).*

## Where things stand

- **Phases 0-6 are done.** Phase 6 added Dagster orchestration (`make dagster`, 61 assets, dbt tests as asset checks, daily schedule off by default) and a Docker stack (`docker compose up`: webserver + daemon), checked by the `docker` job in `ci.yml`.
- **Live:** dashboard https://orginalbusta.github.io/Wholesale-inventory-analytics/ · dbt docs https://orginalbusta.github.io/Wholesale-inventory-analytics/dbt-docs/ · repo https://github.com/orginalbusta/Wholesale-inventory-analytics
- **CI** (`ci.yml`): `build` job (lint, pytest, small dbt build) and `docker` job, on every PR and push to main. **Deploy** (`deploy-pages.yml`) runs on push to main and nightly at 09:00 UTC: medium backfill + catch-up through yesterday → load → dbt build → docs → Evidence → Pages. Pages source is "GitHub Actions".
- **Tests:** 57 pytest tests pass; full `dbt build` = PASS 257, WARN 4 (the planted data-quality issues being caught, by design), ERROR 0.

## Resume prompt (paste to start)

> Read `docs/NEXT_SESSION.md`, then `CLAUDE.md`, `docs/PROGRESS.md` and the top of `docs/DECISIONS.md`. Then start Phase 6.5 from `docs/05_roadmap.md`.

## Phase 6.5 plan (interactive dashboard)

Full spec and acceptance checks in `docs/05_roadmap.md`.

1. What-if reorder policy page (`dashboard/pages/what-if.md`): inputs for service level, lead-time buffer and review period; recompute the `04_dbt_spec.md` reorder formulas per SKU in the browser from `mart_reorder_recommendations` inputs. z comes from a seeded lookup, not an in-browser inverse-normal. Expose any missing inputs in the mart (contract + docs).
2. Parity test: at default inputs, the page's SQL must reproduce the mart exactly.
3. SKU drill-down pages (`dashboard/pages/sku/[sku].md`), linked from the Reorder, Inventory health and What-if tables; keep time series to trailing 12 months so the medium build stays fast.
4. Check which Evidence input components exist in the pinned static edition (v40.1.8) before designing the controls.
5. Then: Phase 7 (CI hardening, slim CI; pin `ubuntu-24.04` before the Ubuntu 26 runner migration), Phase 8 (Snowflake: Harsh starts the 30-day trial right before; auto-suspend + resource monitor), Phase 9 (README polish, license, final review).

## Open items for Harsh

- **Confirm the README "As-is vs. ideal-state" left column** (what he actually built at Craftstones, including "Single analyst, no review process"). It's public now and was kept as he originally wrote it.
- `docs/01_business_context.md` still has assumptions marked for his review (product mix, sourcing countries).
- Optional: a free `FRED_API_KEY` as a repo secret (works without it via FRED's public CSV).

## Environment and gotchas (Windows machine)

- **`make` is not installed.** Run the underlying commands from the `Makefile` directly, or `winget install ezwinports.make`.
- **GitHub CLI:** installed at `"/c/Program Files/GitHub CLI/gh.exe"` (not on the Bash tool's PATH); signed in as `orginalbusta`. Push works over HTTPS without keys.
- **Git identity is repo-local:** Harsh Arya `<190975611+orginalbusta@users.noreply.github.com>` (global config is different; don't change it).
- **Node 24** installed. **Dashboard installs only with `npm ci`** from the committed lockfile (fresh resolution fails: TypeScript 7 / unpublished `@storybook/core`). `evidence preview` doesn't serve; to view a build, copy `dashboard/build` to `.preview/Wholesale-inventory-analytics/` and serve `.preview` (`.claude/launch.json` has a `site-preview` config; both folders are git-ignored).
- **Python file edits from Bash:** run with `PYTHONUTF8=1` (Windows defaults to cp1252 and once truncated a file). Bash heredocs containing certain quote patterns fail to parse; write scripts to the scratchpad with the Write tool instead.
- **dbt + DuckDB in one process:** dbt-duckdb keeps a read-write connection open, so tests query with `duckdb.connect(path)` (not `read_only=True`).
- **sqlfluff** compiles against an in-memory `lint` target (`.sqlfluff`, `profiles.yml`); the pre-commit hook runs serially. Day arithmetic in SQL is plain `date - date` / `date - n` (portable to Snowflake); `dbt.dateadd` only for timestamps.
- **Regenerating data over an existing warehouse needs `dbt build --full-refresh`** (`make all` does this). `make dbt-build` is incremental, for the simulate-day flow.
- The pre-commit end-of-file hook sometimes fixes a file and fails the first commit: re-stage and commit again.

## Useful commands

```bash
uv run python -m generator.generate --scale small            # backfill (1.4s); --scale medium ~5s
uv run python -m generator.generate --scale small --mode catch-up --until yesterday
uv run python -m ingestion.load_erp && uv run python -m ingestion.load_fred
uv run dbt build --full-refresh --project-dir transform --profiles-dir transform
uv run pytest -q                                             # ~70s, builds its own warehouses
uv run sqlfluff lint transform/models transform/tests transform/snapshots
```
