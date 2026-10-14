# Decisions and deviations log

Record any decision that deviates from the specs in `docs/`, or that a reviewer might question. Newest first.

| Date | Decision | Why | Alternatives considered |
|---|---|---|---|
| 2026-10-14 | Build on **dbt Core v1** (`dbt-core` 1.10+ via pip), kept **v2-compatible**: zero deprecation warnings, `--select` not `-m`, no unknown YAML keys, `require-dbt-version` allows `<3.0.0`. Optional stretch: run the project on dbt v2 and note results | dbt v2 (Rust engine) is now the default for new installs, but `dagster-dbt` and the `sqlfluff` dbt templater are built around the Python dbt-core; v1 remains fully supported and job postings still mostly say "dbt Core". v2 validates stricter, so clean v1 code is the safest bridge | dbt v2 only (risk to Dagster and sqlfluff integration) |
| 2026-10-14 | DuckDB is the default warehouse; Snowflake is an optional target | Zero cost, fast CI, and anyone can clone and run it | Snowflake-only (trial expires; CI needs secrets) |
| 2026-10-14 | Use the **Craftstones USA** name, framed as an ideal-state redesign, with prominent disclaimers: all data synthetic; architecture is a proposal, not the production system | Ties the project to Harsh's real experience and gives an honest "as-is vs. ideal-state" story; synthetic data means nothing confidential is published | A fictional company name (loses the connection to real experience); public retail datasets (less domain fit, no lead times or POs) |
