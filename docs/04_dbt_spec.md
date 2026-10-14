# 04: dbt specification

dbt project lives in `transform/`. Layering rules:

- **staging**: 1:1 with sources. Rename, cast, trim, normalize, dedupe re-extracted rows. No joins (except to seeds for mapping). Materialized as **views**.
- **intermediate**: business logic building blocks (joins, dedup across entities, daily spines). Materialized as **ephemeral** or **tables** (tables for heavy ones like daily inventory).
- **marts**: consumer-facing, documented, **contract-enforced** tables. The dashboard reads only marts.

## Sources (`models/staging/erp/_erp__sources.yml`, `models/staging/fred/_fred__sources.yml`)

- `erp`: warehouses, suppliers, products, customers, sales_orders, sales_order_lines, purchase_orders, purchase_order_lines, inventory_movements, cycle_counts. Add **freshness** checks on `sales_orders` and `inventory_movements` using `_extracted_at` (warn 2 days, error 5 days).
- `fred`: observations (one long table: series_id, date, value).

## Seeds (`seeds/`)

| seed | purpose |
|---|---|
| `gem_show_calendar.csv` | show_name, warehouse_id, start_date, end_date per year (approximate dates, labeled as such) |
| `category_mapping.csv` | raw_category_normalized → canonical category |
| `fx_static_rates.csv` | month, currency, units_per_usd for currencies not on FRED (MGA, MAD), plus fallback for all if FRED is unavailable |
| `abc_xyz_policy.csv` | class combo (AX…CZ) → target service level (e.g. AX 0.98 … CZ 0.85). Drives safety stock z-score |

## Snapshots (`snapshots/`)

| snapshot | source | strategy | why |
|---|---|---|---|
| `snap_products` | stg products | `timestamp` on `updated_at` | Price/cost history (SCD2), so margin uses the cost **as of** order date |
| `snap_customers` | stg customers | `check` on `credit_terms`, `sales_rep_id` | Track terms changes |

## Staging models

| model | key cleaning |
|---|---|
| `stg_erp__warehouses` | rename/cast |
| `stg_erp__suppliers` | rename/cast |
| `stg_erp__products` | trim + lowercase category, map via `category_mapping`; canonical SKU via `normalize_sku()` macro |
| `stg_erp__customers` | trim names, lowercase emails, flag `is_email_valid` |
| `stg_erp__sales_orders` | dedupe on order_id keeping latest `updated_at` (planted issue 4) |
| `stg_erp__sales_order_lines` | `normalize_sku()`; split negative quantities into `is_return_line` (issue 6) |
| `stg_erp__purchase_orders` | parse mixed date formats via `parse_mixed_date()` macro (issue 8) |
| `stg_erp__purchase_order_lines` | rename/cast |
| `stg_erp__inventory_movements` | rename/cast; `normalize_sku()` |
| `stg_erp__cycle_counts` | compute `variance_qty`, `variance_pct` |
| `stg_fred__observations` | cast value to numeric, drop FRED's `.` missing markers |

## Macros (`macros/`)

- `normalize_sku(col)`: uppercase, strip non-alphanumerics, re-insert dashes in canonical `XXX-XXX-0000` pattern.
- `parse_mixed_date(col)`: handles `YYYY-MM-DD` and `MM/DD/YYYY`; adapter-dispatched (DuckDB `try_strptime`, Snowflake `try_to_date`).
- `generate_schema_name`: override so schemas are clean (`staging`, `marts`), not `<target>_staging`.
- `cents_to_dollars` style helpers only if needed. Don't add macros nobody uses.

## Intermediate models

| model | grain | logic |
|---|---|---|
| `int_customers__deduplicated` | customer | Match duplicates (normalized name + email); output `customer_id`, `canonical_customer_id` |
| `int_order_lines__enriched` | order line | Join orders + lines + canonical customer + product attributes + **cost as of order date** (from `snap_products`); compute revenue, discount, COGS, margin; exclude cancelled |
| `int_order_lines__orphans` | order line | Lines whose SKU doesn't match any product (issue 9 quarantine) |
| `int_fx_rates__daily` | currency × day | FRED daily FX + static seed, forward-filled over weekends/holidays via a date spine |
| `int_purchase_order_lines__enriched` | PO line | Join PO header; USD cost via FX on order date; lead time actual vs. quoted; on_time flag; fill rate |
| `int_inventory__daily_balance` | SKU × warehouse × day | Cumulative sum of movements over a `dbt_utils.date_spine`. Materialize as **table**; consider incremental |
| `int_sku_demand__daily` | SKU × day | Ordered qty (true demand incl. unfilled), fulfilled qty, unfilled qty. Zero-filled over spine for active SKUs |

## Marts

### core (`models/marts/core/`)
| model | grain | notes |
|---|---|---|
| `dim_date` | day | `dbt_utils.date_spine` (or `dbt_date`); fiscal fields; `is_show_day` from seed |
| `dim_products` | SKU (current) | Canonical attributes + current cost/price + ABC/XYZ class (joined from inventory mart logic, or computed in an int model to avoid cycles) |
| `dim_customers` | canonical customer | Type, state, terms, first/last order date, lifetime revenue |
| `dim_suppliers` | supplier | Plus lead-time stats |
| `dim_warehouses` | warehouse | |
| `fct_order_lines` | order line | **Incremental** (`merge` on `order_line_id`, lookback 7 days on `updated_at` for late updates). Revenue, COGS, margin, fulfilled vs. unfilled qty |
| `fct_orders` | order | Aggregated from lines |
| `fct_purchase_order_lines` | PO line | USD cost, lead times, on-time, fill rate |
| `fct_inventory_daily` | SKU × warehouse × day | On-hand qty, on-hand value at current cost; **incremental** by day |

### inventory (`models/marts/inventory/`)
| model | grain | definition |
|---|---|---|
| `mart_inventory_health` | SKU (all warehouses) | on_hand_qty, on_hand_value_usd, avg_daily_demand_90d, days_of_supply, last_sale_date, days_since_last_sale, **is_dead_stock** (on_hand > 0 and no sale in 180 days), abc_class, xyz_class |
| `mart_reorder_recommendations` | active SKU | See formulas below |
| `mart_stockouts` | SKU × month | stockout_days (on-hand 0 at main warehouse with demand), unfilled_qty, unfilled_revenue_estimate |
| `mart_cycle_count_variance` | SKU × warehouse × month | shrinkage qty/value, variance % |

**ABC/XYZ:**
- ABC on trailing-12-month revenue: A = top SKUs making up 80% of revenue, B = next 15%, C = last 5%.
- XYZ on coefficient of variation of **weekly** demand over trailing 26 weeks: X < 0.5, Y 0.5–1.0, Z > 1.0. (Thresholds as dbt vars.)

**Reorder logic (Phase 1: statistical; later replaced by forecasts):**
```
d̄   = avg daily demand (trailing 90 days, including unfilled demand)
σd   = std dev of daily demand (same window)
L̄   = mean actual lead time (days) for the SKU's primary supplier, trailing 12 months
σL   = std dev of that lead time
z    = norm inverse of the target service level for the SKU's ABC/XYZ class (from seed)
safety_stock   = z × sqrt( L̄ × σd²  +  d̄² × σL² )
reorder_point  = d̄ × L̄ + safety_stock
inventory_position = on_hand + on_order (open PO qty not yet received)
reorder_now    = inventory_position <= reorder_point
suggested_qty  = max(0, reorder_point + d̄ × review_period_days − inventory_position), rounded up to case_pack_qty
```
- `review_period_days` and the z-lookup are dbt vars or seed-driven (z for common service levels can live in the seed to stay warehouse-agnostic).
- Put this calculation in a macro or a clearly named int model so the DS layer can swap `d̄`/`σd` for forecast outputs later. Name columns `demand_mean_daily` / `demand_std_daily` and add a `demand_source` column (`'historical_90d'` now; `'forecast_<model>'` later).

### suppliers (`models/marts/suppliers/`)
| model | grain | definition |
|---|---|---|
| `mart_supplier_performance` | supplier (+ supplier × quarter variant) | PO count, spend USD, on-time rate (arrived ≤ expected + 3 days grace), mean/std actual lead time, quoted-vs-actual gap, fill rate |

### sales (`models/marts/sales/`)
| model | grain | definition |
|---|---|---|
| `mart_sales_monthly` | month × category × channel × customer_type | revenue, COGS, gross margin, orders, units, unfilled revenue |
| `mart_customer_rfm` | canonical customer | recency, frequency, monetary (trailing 12m), quintile scores, segment label (Champions, Loyal, At Risk, Hibernating, New, etc.) |

## Tests

**Generic (in yml):** `unique` + `not_null` on every PK; `relationships` on every FK in marts; `accepted_values` on status/type/class columns; `dbt_utils.unique_combination_of_columns` on composite grains (e.g. `fct_inventory_daily`); `dbt_expectations.expect_column_values_to_be_between` on quantities, prices, margins; email regex test with `severity: warn`.

**Singular (`tests/`):**
- `assert_inventory_never_negative.sql`: `fct_inventory_daily.on_hand_qty >= 0`
- `assert_order_revenue_reconciles.sql`: `fct_orders` total = sum of `fct_order_lines` (within 1 cent)
- `assert_received_not_more_than_ordered.sql`: received ≤ 105% of ordered
- `assert_ledger_matches_cycle_counts.sql`: post-adjustment balance equals counted qty on count dates
- `assert_no_sku_lost_in_normalization.sql`: count of distinct SKUs in lines after normalization, minus orphans, equals matches to `dim_products`

**Unit tests (dbt ≥ 1.8 `unit_tests:`):**
- `normalize_sku` behavior via a staging model unit test (variants → canonical)
- reorder point / safety stock math on a hand-computed fixture
- ABC classification boundaries
- RFM segment assignment

**Model contracts:** enable `contract: {enforced: true}` on all `marts/` models with explicit `data_type`s.

**Exposures:** declare the Evidence dashboard as an exposure depending on the marts it reads.

**Freshness and docs:** `dbt source freshness` runs in the Dagster job; every model and column in marts has a description; add a `docs/overview.md` doc block for the dbt docs landing page.

## Vars (in `dbt_project.yml`)

```yaml
vars:
  dead_stock_days: 180
  demand_window_days: 90
  lead_time_window_days: 365
  review_period_days: 14
  on_time_grace_days: 3
  abc_thresholds: {a: 0.80, b: 0.95}
  xyz_thresholds: {x: 0.5, y: 1.0}
  incremental_lookback_days: 7
```

## Optional stretch (only after Definition of Done)

- dbt **semantic layer / MetricFlow** metrics for revenue, margin, fill rate
- `dbt-project-evaluator` package to audit project structure
- Elementary (`elementary-data`) for data observability reports
