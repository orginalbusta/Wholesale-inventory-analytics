# Dashboard (Evidence)

A static [Evidence](https://evidence.dev) site that reads **only** the dbt `marts` schema of the
DuckDB warehouse (`../warehouse/craftstones.duckdb`). Every page carries the disclaimer: synthetic
data, an ideal-state design, not the production system at Craftstones.

Pages: Overview (`pages/index.md`), Reorder, Inventory health, Suppliers, Sales & customers,
What-if reorder policy (`pages/what-if.md`, recalculates the reorder policy in the browser), All SKUs
(`pages/sku/index.md`) and one SKU detail page (`pages/sku/detail.md`, at `/sku/detail/?id=<SKU>`).
Source queries live in `sources/marts/*.sql`; the dbt exposure `inventory_dashboard` lists the
marts they depend on.

## Run locally

Build the warehouse first (`make all` from the repo root), then:

```bash
make dashboard       # npm ci, extract sources, start the dev server
```

## Build the static site

```bash
npm ci
npm run sources
npm run build:strict   # writes ./build; the deploy workflow publishes it to GitHub Pages
```

## Why this setup

This is the open-source, static-site edition of Evidence, scaffolded from the official
`evidence-dev/template` `legacy` branch. Evidence's newer product (Evidence Studio) is hosted and
needs an account; the static edition builds plain files that GitHub Pages serves for free.
Installs use the committed `package-lock.json` (`npm ci`): resolving fresh versions no longer
works because some transitive packages have been unpublished. See `docs/DECISIONS.md`.
