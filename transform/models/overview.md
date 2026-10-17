{% docs __overview__ %}

# Craftstones Data Platform: an ideal-state redesign

> **All data is synthetic**, and **this is an ideal-state design, not the system in use at
> Craftstones USA.** No real customers, suppliers, prices, costs or volumes appear anywhere.

This dbt project turns a (simulated) wholesale stone distributor's ERP data into tested,
documented tables that answer one question: **which SKUs should we reorder, when, and how
much, and where is cash tied up in dead stock?**

## Layers

| Layer | Schema | What it does |
|---|---|---|
| Sources | `raw_erp`, `raw_fred` | Append-only extracts loaded by dlt. Never modified by dbt. |
| Staging | `staging` | One view per source table: latest version per key, renamed, cast, cleaned. Deliberately planted data-quality issues are fixed or flagged here. |
| Intermediate | `intermediate` | Business logic: customer de-duplication, cost as of order date, daily stock balances, true demand (incl. stockouts), ABC/XYZ, reorder inputs. |
| Marts | `marts` | Contract-enforced tables the dashboard reads: dimensions, facts, and inventory, supplier and sales marts. |
| Snapshots | `snapshots` | SCD2 history of product prices and customer terms. |

## Where to start

- **`mart_reorder_recommendations`**: reorder point from demand *and* supplier lead-time
  variability, with ABC/XYZ service levels, a reorder-now flag and a suggested quantity.
- **`mart_inventory_health`**: stock, value, days of supply and dead stock per SKU.
- **`mart_supplier_performance`**: on-time rate and quoted vs. actual lead times.

Open the lineage graph (bottom right) to follow any mart back to its raw source.

Live dashboard: [https://orginalbusta.github.io/Wholesale-inventory-analytics/](https://orginalbusta.github.io/Wholesale-inventory-analytics/) (including a [what-if reorder policy](https://orginalbusta.github.io/Wholesale-inventory-analytics/what-if/) page).
Source code, findings and design decisions: [the GitHub repo](https://github.com/orginalbusta/Wholesale-inventory-analytics) and its [decision log](https://github.com/orginalbusta/Wholesale-inventory-analytics/blob/main/docs/DECISIONS.md).

{% enddocs %}
