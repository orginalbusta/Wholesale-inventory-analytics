# 06: Future data science layer (NOT IN CURRENT SCOPE)

Not built yet. It is listed so the current design doesn't block it.

## Planned additions

1. **SKU-level demand forecasting**
   - Models: seasonal naive baseline → ETS / gradient boosting with calendar, show-window, and FRED regressors → hierarchical reconciliation (SKU → category → total).
   - Backtesting with rolling origin; metrics: WAPE, bias, plus a **business metric**: simulated stockout days and inventory value under forecast-driven vs. historical reorder points.
   - Output table `forecast_daily` (sku, date, forecast_mean, forecast_std, model_name, run_id) written back to the warehouse and read by dbt as a source.
   - Swap into reorder logic by changing `demand_source`.
   - Validate against `data/_truth/` (the generator knows the real demand process).

2. **Experimentation / causal inference**
   - Simulated pricing or promotion A/B test (generator adds a treatment assignment to a subset of customers or SKUs), with power analysis, analysis, and a business recommendation.
   - Difference-in-differences or synthetic control for the effect of a past show or promotion.

3. **"Ask the data" LLM interface (stretch)**
   - Natural-language questions answered by generating SQL against documented marts (using dbt docs and model contracts as context), with guardrails (read-only, whitelisted schemas, row limits).

## Design hooks already in place (keep them working)

- `mart_reorder_recommendations` has `demand_mean_daily`, `demand_std_daily`, `demand_source` columns.
- `int_sku_demand__daily` includes **unfilled demand**, so forecasts train on true demand, not censored sales.
- `data/_truth/` preserves ground-truth demand parameters.
- `dim_date` includes show-window flags usable as forecast features.
- Dagster assets are structured so a `forecast` asset can sit between dbt intermediate models and the reorder mart.
