# 03: Synthetic data specification

This is the source of truth for `generator/`. The goal is data that is **realistic enough that the analysis produces believable, interesting findings**, and **messy enough that dbt staging and tests have real work to do**.

Every value is generated. Never seed the generator with real Craftstones names, prices, volumes or supplier relationships.

All randomness flows from a single seed in `generator/config.yaml`. Same seed + same scale = byte-identical output.

## Scales

| Scale | Date range | Customers | SKUs | Suppliers | Orders (approx) | Order lines (approx) | Use |
|---|---|---|---|---|---|---|---|
| `small` | 2025-04-01 → 2026-09-30 (18 mo) | 150 | 200 | 15 | ~12k | ~60k | CI, fast local dev |
| `medium` | 2023-10-01 → 2026-09-30 (36 mo) | 650 | 1,200 | 60 | ~120k | ~850k–1M | Portfolio numbers, Snowflake demo |

Volumes are targets, not hard requirements; keep within ±25%.

## Output format

- One parquet file per table per run: `data/raw/erp/<table>/<run_id>.parquet` (backfill writes `run_id=backfill`; each simulated day writes `run_id=<YYYY-MM-DD>`).
- Every table gets `_extracted_at` (timestamp of the generator run). Mutable tables also carry `updated_at` (business timestamp of the last change).
- `data/_truth/` holds **ground-truth parameters** the generator used (per-SKU base demand, seasonality profile, true supplier lead-time distributions, planted-issue row IDs). This is **never loaded into the warehouse**. It exists so tests (and the future DS layer) can check that analysis recovers the truth.

## Reference dimensions

### `warehouses`
| column | type | notes |
|---|---|---|
| warehouse_id | str | `SD-MAIN`, `SHOW-TUC`, `SHOW-DEN` |
| warehouse_name | str | |
| warehouse_type | str | `main` / `show` |
| city, state | str | San Diego CA; Tucson AZ; Denver CO |
| is_seasonal | bool | true for show locations |

### `suppliers`
| column | type | notes |
|---|---|---|
| supplier_id | str | `SUP-0001` … |
| supplier_name | str | Fictional (Faker company names + stone-trade suffixes like "Gems Export", "Minerals Ltda", "Stone Craft") |
| country | str | Weighted: India 30%, Brazil 20%, China 15%, Madagascar 8%, Mexico 8%, Morocco 7%, USA 12% |
| currency | str | INR, BRL, CNY, MGA, MXN, MAD, USD matching country |
| payment_terms | str | `PREPAID`, `NET30`, `NET60`, `50_50` |
| min_order_value_usd | float | 500–10,000 |
| created_at | date | |

**Hidden truth (write to `_truth/`, not to the table):** per-supplier lead-time distribution, lognormal with mean by region (USA 10–20 days, Mexico 20–35, overseas 45–110) and a reliability factor (some suppliers have high variance and frequent late/short deliveries). Short-shipment probability: 0–15% per supplier.

### `products`
| column | type | notes |
|---|---|---|
| sku | str | Canonical form `AMT-PLS-0042` (material code, category code, number) |
| product_name | str | e.g. "Amethyst Polished Point, Large" |
| category | str | `Polished Stones`, `Rough Minerals`, `Crystal Clusters`, `Tumbled Stones`, `Jewelry Components`, `Decor & Landscape` |
| material | str | ~30 materials (amethyst, rose quartz, clear quartz, agate, jasper, labradorite, lapis lazuli, malachite, tiger eye, obsidian, selenite, citrine, fluorite, pyrite, jade, turquoise, onyx, marble, calcite, aventurine, carnelian, moonstone, hematite, rhodonite, sodalite, smoky quartz, garnet, tourmaline, petrified wood, river rock) |
| primary_supplier_id | str | FK suppliers; material/origin-consistent where plausible |
| unit_of_measure | str | `each` for most; `lb` for tumbled/rough/landscape |
| unit_cost_usd | float | lognormal by category |
| list_price_usd | float | cost × markup (1.8–3.5 by category) |
| case_pack_qty | int | 1, 6, 12, 24, 50 |
| launch_date | date | most before range start; ~10% launched during range |
| discontinued_date | date, nullable | ~8% discontinued during range |
| is_active | bool | |
| updated_at | timestamp | |

**Mutations over time:** ~2% of SKUs per month get a cost change (±3–15%, more for FX-exposed origins), and list price follows with a lag of 0–30 days. These changes power the **`snap_products`** snapshot.

### `customers`
| column | type | notes |
|---|---|---|
| customer_id | str | `CUS-00001` … |
| customer_name | str | Fictional businesses |
| customer_type | str | `retail_shop` 35%, `jewelry_maker` 20%, `online_reseller` 18%, `interior_designer` 10%, `landscaper` 8%, `wholesaler` 5%, `metaphysical_store` 4% |
| contact_email | str, nullable | |
| state | str | US states, weighted toward CA, AZ, TX, CO, FL, NY, OR, WA |
| credit_terms | str | `PREPAID`, `NET30`, `NET60` (changes over time → `snap_customers`) |
| sales_rep_id | str | 4 reps: `REP-01`…`REP-04` |
| first_order_date | date | |
| created_at, updated_at | timestamp | |

## Transactional tables

### `sales_orders`
| column | type | notes |
|---|---|---|
| order_id | str | `SO-<yyyymm>-<seq>` |
| customer_id | str | FK |
| order_date | date | |
| channel | str | `phone_email` 35%, `b2b_portal` 30%, `gem_show` 20% (only during show windows), `marketplace` 15% |
| warehouse_id | str | `SD-MAIN` normally; show location for gem_show orders |
| status | str | `placed` → `shipped` → `delivered`; ~3% `cancelled`; ~2% `returned` |
| ship_date | date, nullable | 0–5 business days after order if in stock |
| order_discount_pct | float | 0 for most; 5–15% for wholesalers and show deals |
| sales_rep_id | str | |
| updated_at | timestamp | changes when status changes |

### `sales_order_lines`
| column | type | notes |
|---|---|---|
| order_line_id | str | `<order_id>-<line_no>` |
| order_id | str | FK |
| line_no | int | |
| sku | str | FK (see planted issues: SKU variants) |
| quantity | float | ordered quantity (in product UoM); must respect case packs mostly |
| quantity_fulfilled | float | ≤ quantity; less when stock ran out (**this is how stockouts show up**) |
| unit_price_usd | float | list price at time of order, with occasional negotiated deviation |
| line_discount_pct | float | |

### `purchase_orders`
| column | type | notes |
|---|---|---|
| po_id | str | `PO-<yyyymm>-<seq>` |
| supplier_id | str | FK |
| order_date | date | |
| expected_arrival_date | date | order_date + supplier's *quoted* lead time (optimistic vs. truth) |
| actual_arrival_date | date, nullable | from hidden true lead-time distribution; null if still in transit |
| status | str | `open`, `in_transit`, `received`, `partially_received`, `cancelled` |
| currency | str | supplier currency |
| updated_at | timestamp | |

### `purchase_order_lines`
| column | type | notes |
|---|---|---|
| po_line_id | str | |
| po_id | str | FK |
| sku | str | FK |
| quantity_ordered | float | |
| quantity_received | float, nullable | short shipments per supplier truth; null until received |
| unit_cost_local | float | in supplier currency (convert to USD with FRED FX in dbt) |

### `inventory_movements` (ledger, the source of truth for stock levels)
| column | type | notes |
|---|---|---|
| movement_id | str | |
| movement_ts | timestamp | |
| warehouse_id | str | |
| sku | str | |
| movement_type | str | `receipt` (+, from PO), `sale` (−, from order line fulfillment), `return` (+), `transfer_out` (−) / `transfer_in` (+) (to/from show locations), `adjustment` (±, from cycle counts / damage) |
| quantity | float | signed |
| reference_id | str | po_line_id / order_line_id / transfer id / count id |

### `cycle_counts`
| column | type | notes |
|---|---|---|
| count_id | str | |
| count_date | date | |
| warehouse_id | str | |
| sku | str | |
| system_qty | float | ledger balance at count time |
| counted_qty | float | system_qty plus shrinkage/noise (−3% to +1% typical; a few big misses) |

Each A-class SKU is counted ~monthly, others ~quarterly. Every count with a variance produces an `adjustment` movement.

## How demand is generated (make the findings interesting)

Per SKU per day, expected demand = `base_rate × trend × category_seasonality × show_effect × lifecycle × price_effect`, then draw a **negative binomial** count (overdispersed: B2B demand is lumpy). Then group demand into orders by customer.

- **base_rate**: Pareto across SKUs so ~20% of SKUs produce ~75–80% of revenue.
- **trend**: mild per-category drift (e.g. Jewelry Components +8%/yr, Decor & Landscape −3%/yr).
- **category_seasonality**: Jewelry/Crystals peak Oct–Nov; Decor & Landscape peak Mar–May; everything dips in July.
- **show_effect**: during show windows (see `seeds/gem_show_calendar.csv`), demand for show-relevant categories ×2.5–4 via the `gem_show` channel at the show warehouse.
- **lifecycle**: ramp-up after launch_date; decay to zero after discontinued_date.
- **price_effect**: mild elasticity after price increases.
- **Customer behavior**: each customer has an order frequency (Gamma-distributed), basket size, and category affinity by customer_type. ~15% of customers churn (stop ordering) during the range; new customers arrive steadily.

## How purchasing is generated (create dead stock and stockouts on purpose)

Simulate a **naive purchasing policy** like the real company's gut-feel process. This is what the platform's reorder logic will improve on:
- Reorder a SKU when on-hand falls below a fixed "eyeballed" threshold, using the *quoted* (optimistic) lead time.
- Before each show, bulk-buy show categories with an over-optimism multiplier (1.3–2.0×). This produces dead stock on the slower SKUs.
- High-variance suppliers plus optimistic lead times means fast movers run out right before peaks. This produces stockouts (`quantity_fulfilled < quantity`).

Inventory must be simulated day by day so the ledger is internally consistent: on-hand never goes below 0 in the true simulation.

## Planted data-quality issues (dbt staging + tests must handle these)

Rates are configurable in `config.yaml`. Record every planted row's ID in `data/_truth/planted_issues.parquet` so pytest can verify detection.

| # | Issue | Where | Approx rate | Expected handling in dbt |
|---|---|---|---|---|
| 1 | Duplicate customers (same business, name variants such as "Rock & Gem Shop" vs "Rock and Gem Shop LLC", same email) | customers | 2% | `int_customers__deduplicated` with a match rule; map old IDs → surviving ID |
| 2 | Inconsistent category labels (`polished stones`, `Polished  Stones `, `POLISHED`) | products | 5% | Trim/case-normalize + `seeds/category_mapping.csv` |
| 3 | SKU code variants in order lines (`amt-pls-0042`, `AMTPLS0042`) | sales_order_lines | 1% | Normalize to canonical format in staging; relationships test passes after |
| 4 | Duplicate rows from re-extraction (same PK, same or newer `updated_at`) | sales_orders | 0.5% | Dedupe on PK keeping latest `updated_at` |
| 5 | Late-arriving status updates (order status changes days later, delivered via simulate-day) | sales_orders | ongoing | Incremental model with lookback window; merge on PK |
| 6 | Returns encoded as negative quantity lines instead of `returned` status | sales_order_lines | 0.3% | Split into returns in staging; test that sales quantities are ≥ 0 |
| 7 | Null or malformed emails | customers | 4% | Accept null; flag malformed (`dbt_expectations` regex test with `warn` severity) |
| 8 | Mixed date string formats in one raw column (`2025-03-04`, `03/04/2025`) | purchase_orders.expected_arrival_date (raw as string) | 2% | Parse both in staging; test all parse |
| 9 | Orphan order lines pointing to non-existent SKUs | sales_order_lines | 0.1% | Relationships test with `warn` severity; quarantine to `int_order_lines__orphans` |
| 10 | Cycle count with big miss (lost/stolen stock) | cycle_counts | rare | Surfaces in shrinkage analysis |

## Public data (FRED)

Loaded by `ingestion/load_fred.py` (needs free `FRED_API_KEY`; if missing, skip with a warning and dbt falls back to a static FX seed so the build never breaks):

| Series ID | Meaning | Use |
|---|---|---|
| `DEXINUS` | INR per USD (daily) | Convert INR PO costs |
| `DEXBZUS` | BRL per USD (daily) | Convert BRL PO costs |
| `DEXCHUS` | CNY per USD (daily) | Convert CNY PO costs |
| `DEXMXUS` | MXN per USD (daily) | Convert MXN PO costs |
| `RSXFS` | US retail sales excl. food services (monthly) | Macro context; later a forecast regressor |
| `UMCSENT` | Consumer sentiment (monthly) | Macro context; later a forecast regressor |

MGA and MAD are not on FRED: use `seeds/fx_static_rates.csv` (monthly approximate rates, clearly labeled as approximations) and document this in DECISIONS.md. The generator must use the **same FX values** when creating `unit_cost_local` so USD costs reconcile. Simplest approach: the generator reads the same seed/FRED cache that dbt uses.

Verify these series IDs still exist before building (FRED occasionally discontinues series).
