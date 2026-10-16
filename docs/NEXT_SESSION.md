# Next session: pick up here

*Updated 2026-10-16 at the end of Phase 8. Read this first, then `CLAUDE.md`, `docs/PROGRESS.md` and `docs/DECISIONS.md` (newest entries at the top).*

## Where things stand

- **Phases 0-8 are done.** Phase 8 ran the medium pipeline on Snowflake: dbt build passes and all 18 marts match DuckDB exactly. Phase 7 pinned the runners to `ubuntu-24.04`, made dbt failures readable in CI, and fixed the stale-cache errors after deploys (each deploy carries the previous deploy's hashed files). Phase 6.5 added the what-if reorder policy page and per-SKU drill-down pages (rendered in the browser via a 404.html SPA fallback). Phase 6 added Dagster orchestration (`make dagster`, 61 assets, dbt tests as asset checks, daily schedule off by default) and a Docker stack (`docker compose up`: webserver + daemon), checked by the `docker` job in `ci.yml`.
- **Live:** dashboard https://orginalbusta.github.io/Wholesale-inventory-analytics/ · dbt docs https://orginalbusta.github.io/Wholesale-inventory-analytics/dbt-docs/ · repo https://github.com/orginalbusta/Wholesale-inventory-analytics
- **CI** (`ci.yml`): `build` job (lint, pytest, small dbt build) and `docker` job, on every PR and push to main. **Deploy** (`deploy-pages.yml`) runs on push to main and nightly at 09:00 UTC: medium backfill + catch-up through yesterday → load → dbt build → docs → Evidence → Pages. Pages source is "GitHub Actions".
- **Tests:** 67 pytest tests pass; full `dbt build` = PASS 267, WARN 4 (the planted data-quality issues being caught, by design), ERROR 0.

## Resume prompt (paste to start)

> Read `docs/NEXT_SESSION.md`, then `CLAUDE.md`, `docs/PROGRESS.md` and the top of `docs/DECISIONS.md`. Then start Phase 9 from `docs/05_roadmap.md`.

## Phase 9 plan (polish for hiring managers)

From `docs/05_roadmap.md`. Accept when someone unfamiliar with the project understands the business problem, the architecture and the main findings within 2 minutes of opening the README.

1. README final pass: 3-5 findings written as business decisions, each with its number and the mart it came from (numbers from the pinned medium snapshot, seed 42, through 2026-09-30; never invented). Point to the what-if page as the interactive version of the reorder finding.
2. "Design decisions and trade-offs" and "If I had more time" sections (the latter points to `docs/06_future_ds_layer.md`).
3. Repo hygiene: MIT `LICENSE` file (pyproject already says MIT), badges, no secrets, no large files, decide what to do with `KICKOFF_PROMPT.md` and `docs/NEXT_SESSION.md` in a public repo.
4. Read the README cold, as a hiring manager would; tighten.

## Snowflake notes (Phase 8 is done)

- Everything Snowflake runs through `uv run --env-file .env ...`; on Windows PowerShell set `$env:WAREHOUSE = "snowflake"` for the dlt loads only (bash `WAREHOUSE=snowflake cmd` doesn't work there). Commands: `snowflake/README.md` section 6.
- Optional: exact credits from `snowflake.account_usage.warehouse_metering_history` (ACCOUNTADMIN), and a Snowsight screenshot for the README. The trial expires 30 days after Harsh started it; `snowflake/teardown.sql` removes everything.

## Open items for Harsh

- Optional, for the README: run the credits query in `snowflake/README.md` (exact Phase 8 cost) and take a Snowsight screenshot or two.
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
- **Dagster runs dbt from inside `transform/`.** `definitions.py` makes `DUCKDB_PATH` absolute, and any `dbt parse` whose cache Dagster will reuse must use an absolute `--project-dir` (dbt stores seed paths relative to the project dir as given).
- **Dashboard preview with SKU pages:** SKU pages are only served through `404.html`, so `python -m http.server` can't show them; `scripts/serve_pages_preview.py` (also the `pages-like-preview` entry in `.claude/launch.json`) serves `404.html` for missing paths, like GitHub Pages. Copy `dashboard/build` to `.preview/Wholesale-inventory-analytics/` first.
- `make dagster` keeps run history in `.dagster_home/`; the `dagster` entry in `.claude/launch.json` starts the same UI in the browser pane.
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
