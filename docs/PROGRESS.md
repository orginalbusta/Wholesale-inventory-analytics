# Progress log

Update at the end of every phase: what was built, acceptance check results, known issues, next step.

| Phase | Status | Date | Notes |
|---|---|---|---|
| 0: Environment and skeleton | done | 2026-10-14 | All acceptance checks pass (see below) |
| 1: Synthetic data generator | not started | | |
| 2: Ingestion (dlt) | not started | | |
| 3: dbt staging, seeds, snapshots | not started | | |
| 4: Intermediate and marts | not started | | |
| 5: Dashboard, docs site, README v1 | not started | | |
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
