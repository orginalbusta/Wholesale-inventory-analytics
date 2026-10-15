# Next session: pick up here

*Written 2026-10-15 at the end of Phase 5. Read this first, then `CLAUDE.md`, `docs/PROGRESS.md` and `docs/DECISIONS.md` (newest entries at the top).*

## Where things stand

- **Phases 0-5 are done**: the minimum shippable version. Last commit: `9b48338 docs: close phase 5 with live site checks` (pushed, working tree clean apart from this file).
- **Live:** dashboard https://orginalbusta.github.io/Wholesale-inventory-analytics/ · dbt docs https://orginalbusta.github.io/Wholesale-inventory-analytics/dbt-docs/ · repo https://github.com/orginalbusta/Wholesale-inventory-analytics
- **CI** (`ci.yml`) runs on every PR and push to main (~2.5 min, green). **Deploy** (`deploy-pages.yml`) runs on push to main and nightly at 09:00 UTC: medium backfill + catch-up through yesterday → load → dbt build → docs → Evidence → Pages (~2.5 min, green). Pages source is set to "GitHub Actions".
- **Tests:** 52 pytest tests pass; full `dbt build` = PASS 257, WARN 4 (the 4 warnings are planted data-quality issues being caught, by design), ERROR 0.

## Resume prompt (paste to start)

> Read `docs/NEXT_SESSION.md`, then `CLAUDE.md`, `docs/PROGRESS.md` and the top of `docs/DECISIONS.md`. Then start Phase 6 from `docs/05_roadmap.md`.

## Phase 6 plan (Dagster + Docker)

From `docs/05_roadmap.md`. Accept when `make dagster` shows the full asset lineage, materializing all assets succeeds, and `docker compose up` brings up the UI.

1. Check the current Dagster / dagster-dbt APIs first (pinned: dagster 1.13, dagster-dbt 0.29; the API has changed across releases). Expect `DbtProject`, `@dbt_assets`, `DbtCliResource`.
2. `orchestration/craftstones_dagster/definitions.py` (stub with the plan in its docstring): assets `simulate_day` (or `catch_up`) → `erp_raw` / `fred_raw` (call `ingestion.load_erp.load_erp` / `ingestion.load_fred.load_fred`) → dbt assets from the manifest, with dbt sources mapped to the raw assets so lineage is end to end → `dbt source freshness` as an asset check. Daily schedule ~06:00 America/Los_Angeles, `default_status=STOPPED`.
3. dbt tests should surface as Dagster asset checks (dagster-dbt does this from the manifest).
4. `Dockerfile` / `docker-compose.yml` exist from the scaffold: pin the `uv` image (currently `ghcr.io/astral-sh/uv:latest`), use Python 3.12, run webserver + daemon.
5. **Docker is not installed** on Harsh's machine (`winget install Docker.DockerDesktop`, needs WSL2). Ask before relying on it; the Docker acceptance check can also run in CI.
6. Then: **Phase 6.5 (interactive dashboard, added 2026-10-15: what-if reorder policy page + SKU drill-down pages; see roadmap)**, Phase 7 (CI hardening, slim CI), Phase 8 (Snowflake: Harsh starts the 30-day trial right before; auto-suspend + resource monitor), Phase 9 (README polish, license, final review).

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
