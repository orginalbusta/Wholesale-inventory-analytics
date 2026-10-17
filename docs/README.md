# Documentation

| File | What it is |
|---|---|
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | **Start here.** One-page, top-down overview: pipeline layers, tools, skills, design decisions |
| [02_architecture.md](02_architecture.md) | Architecture as built: data flow, stack, dbt targets, schemas, repo layout |
| [DECISIONS.md](DECISIONS.md) | Every design decision and deviation from the plan, with reasons and alternatives (newest first) |
| [PROGRESS.md](PROGRESS.md) | What each build phase delivered and how it was checked |
| [01_business_context.md](01_business_context.md) | The company, the people who'd use the platform, and the decisions it supports |
| [03_data_spec.md](03_data_spec.md), [04_dbt_spec.md](04_dbt_spec.md) | The original specs for the synthetic data and the dbt project |
| [05_roadmap.md](05_roadmap.md) | The phased build plan with acceptance criteria |
| [06_future_ds_layer.md](06_future_ds_layer.md) | Planned next step: forecasting and other data-science work (not built) |

Files 01 and 03-06 were written before the build as its plan. Where the build deliberately
did something different, the reason is in [DECISIONS.md](DECISIONS.md). All data in this
project is synthetic, and the design is an ideal-state proposal, not the system in use at
Craftstones USA.
