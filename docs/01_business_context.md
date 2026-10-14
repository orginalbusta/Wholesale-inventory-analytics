# 01: Business context

## Framing

This project is an **ideal-state redesign** of the data platform for **Craftstones USA**, based on Harsh's experience as its sole data analyst (Sep 2023 to Apr 2026). **All data is synthetic**, and the architecture is a proposed design, **not** the system in use at Craftstones.

> **Harsh: review this section.** Details below marked *(assumption)* were written to make the simulation interesting. Correct them to match reality at a level you're comfortable sharing publicly, or keep them as clearly labeled simulation assumptions. Don't add anything confidential.

## As-is (what existed, from Harsh's resume)

- SQL databases plus spreadsheets, integrated by ETL pipelines Harsh built
- Tableau dashboards that replaced manual reporting (saving 6+ hours per week)
- A Python regression demand forecast on 3+ years of sales history, used for inventory decisions
- Customer segmentation (clustering, RFM)
- A new inventory management system, which Harsh evaluated and rolled out

## Ideal-state (what this project builds)

A warehouse-centered platform with raw → staging → marts layers in dbt, automated tests on every model, an orchestrated daily pipeline, version-controlled dashboards, CI on every change, and a reorder system built on supplier lead-time variability and ABC/XYZ service levels. The forecasting work plugs into it later as a swappable demand input.

## The company (simulation profile)

**Craftstones USA** is a ~20-person wholesale distributor based in San Diego, CA. For the simulation, it imports *(assumption: product mix and sourcing countries)* polished stones, rough minerals, crystal clusters, tumbled stones, jewelry components, and decor/landscape stone from suppliers in India, Brazil, China, Madagascar, Mexico, Morocco and the US, and sells to retail shops, jewelry makers, interior designers, landscapers, and online resellers across the US.

Characteristics that drive the simulated data *(assumptions unless Harsh confirms them)*:

- **~1,200 active SKUs**, highly skewed: a small share of SKUs drives most revenue (Pareto).
- **Long, variable supplier lead times** (2 to 16 weeks), mostly ocean freight from overseas suppliers, priced in local currency.
- **Gem show seasonality.** Large trade shows (notably a major show in Tucson, AZ in late Jan to mid Feb, and a fall show in Denver in September) drive spikes in both purchasing and sales. The company moves stock to a temporary show location for these.
- **Category seasonality.** Jewelry components and gift-oriented crystals peak before the holidays (Oct to Nov); landscape/decor stone peaks in spring (Mar to May).
- **Two-plus inventory locations:** main warehouse in San Diego, plus a seasonal show location.
- **Historically ran on spreadsheets plus a small ERP.** Data is messy: duplicate customers, inconsistent category labels, SKU code variants, late-arriving status updates.

## The problem

Inventory is the largest use of cash for a distributor like this. The simulation starts from a **baseline purchasing policy** (fixed reorder thresholds, quoted rather than actual lead times, optimistic buying for shows) so the platform has measurable problems to fix. This baseline is a simulation device, not a description of how Craftstones actually purchased. It produces three problem types:

1. **Stockouts on fast movers** right before peak season, losing sales.
2. **Dead stock**: slow-moving SKUs overbought for shows sit for 6+ months, tying up cash.
3. **Unmeasured supplier reliability**: some suppliers routinely deliver late or short, and quoted lead times understate reality.

The README's findings compare the platform's recommendations against this simulated baseline.

## Stakeholders and the decisions they make

| Stakeholder | Decision | What they need from the platform |
|---|---|---|
| Owner / GM | How much cash to commit to inventory this quarter; which product lines to grow or cut | Inventory value by category, dead-stock value, margin by category, trend |
| Purchasing lead | What to reorder, when, from whom, how much | Reorder recommendations per SKU (reorder point, suggested qty), supplier lead-time stats |
| Sales lead | Which customers to prioritize; what to bring to the next show | Customer RFM segments, top SKUs by season, fill rate by customer type |
| Warehouse / ops | Where inventory discrepancies are | Cycle count variance, stock levels by location |

## Questions the platform must answer (these become marts and dashboard pages)

1. **Inventory health:** What is on hand, what is it worth, how many days of supply does each SKU have, and which SKUs are dead stock (no sales in 180+ days with on-hand > 0)?
2. **ABC/XYZ classification:** Which SKUs are A/B/C by revenue contribution, and X/Y/Z by demand variability? (Drives how much safety stock each deserves.)
3. **Reorder recommendations:** For each active SKU: average daily demand, demand variability, supplier lead time (mean and std), safety stock, reorder point, current position, and a "reorder now?" flag with a suggested quantity.
4. **Stockouts and fill rate:** How often did we run out of the A items, and what demand went unfilled?
5. **Supplier performance:** On-time %, average and variability of lead time, fill rate (received / ordered), by supplier.
6. **Sales performance:** Revenue, margin, and orders by month, category, channel, and customer type; customer RFM segments.

## Success metrics to report in the README (once real numbers exist)

- Dead-stock value and share of total inventory value
- Share of A-class SKUs currently below reorder point
- Stockout days for A-class SKUs in the last 12 months
- Supplier on-time rate range (best vs. worst supplier)
- Pipeline facts: rows processed, number of dbt models/tests, build time

## Out of scope for now

- Demand **forecasting** models and **experiments** (see `06_future_ds_layer.md`). Phase-1 reorder logic uses historical demand statistics, designed so a forecast can replace them later.
- Real-time streaming, multi-company tenancy, auth.
