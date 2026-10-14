"""Print sanity statistics for generated data: rows per table, revenue by month, top categories,
and the signals the platform is meant to find (stockouts, dead stock, supplier lateness).

Reads the raw parquet directly with DuckDB (nothing is loaded into the warehouse).

Run: uv run python -m generator.summary [--output-root .]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from generator.config import REPO_ROOT


def summarize(root: Path) -> None:
    raw = (root / "data" / "raw" / "erp").as_posix()
    mapping = (REPO_ROOT / "transform" / "seeds" / "category_mapping.csv").as_posix()
    con = duckdb.connect()

    def table(name: str) -> str:
        return f"read_parquet('{raw}/{name}/*.parquet', union_by_name = true)"

    con.execute(f"""
        create view orders as
            select * from {table("sales_orders")}
            qualify row_number() over (partition by order_id order by updated_at desc) = 1;
        create view lines as select * from {table("sales_order_lines")};
        create view products as
            select p.*, m.category as category_clean
            from {table("products")} as p
            left join read_csv('{mapping}') as m
                on m.raw_category_normalized = regexp_replace(lower(trim(p.category)), '\\s+', ' ', 'g');
        create view revenue_lines as
            select o.order_date, o.channel, o.status, l.*,
                   p.category_clean as category,
                   p.sku as canonical_sku,
                   l.quantity_fulfilled * l.unit_price_usd
                       * (1 - l.line_discount_pct / 100) * (1 - o.order_discount_pct / 100) as revenue
            from lines as l
            join orders as o using (order_id)
            left join products as p
                on p.sku = regexp_replace(upper(trim(l.sku)), '[^A-Z0-9]', '', 'g')[1:3] || '-'
                    || regexp_replace(upper(trim(l.sku)), '[^A-Z0-9]', '', 'g')[4:6] || '-'
                    || regexp_replace(upper(trim(l.sku)), '[^A-Z0-9]', '', 'g')[7:10]
            where o.status <> 'cancelled' and l.quantity > 0;
    """)

    print("Rows per table")
    for name in sorted(p.name for p in (root / "data" / "raw" / "erp").iterdir()):
        n = con.execute(f"select count(*) from {table(name)}").fetchone()[0]
        print(f"  {name:<24} {n:>10,}")

    print("\nRevenue by month (fulfilled, net of discounts)")
    for month, rev, n_orders in con.execute("""
        select strftime(date_trunc('month', order_date), '%Y-%m'), sum(revenue), count(distinct order_id)
        from revenue_lines group by 1 order by 1
    """).fetchall():
        print(f"  {month}  ${rev:>12,.0f}  {n_orders:>6,} orders")

    print("\nRevenue by category")
    for cat, rev, share in con.execute("""
        select coalesce(category, '(orphan sku)'), sum(revenue),
               sum(revenue) / sum(sum(revenue)) over ()
        from revenue_lines group by 1 order by 2 desc
    """).fetchall():
        print(f"  {cat:<22} ${rev:>12,.0f}  {share:6.1%}")

    print("\nChannel mix (orders)")
    for ch, share in con.execute("""
        select channel, count(*) / sum(count(*)) over () from orders group by 1 order by 2 desc
    """).fetchall():
        print(f"  {ch:<14} {share:6.1%}")

    top20, fill_rate, a_unfilled = con.execute("""
        with by_sku as (
            select canonical_sku, sum(revenue) as rev
            from revenue_lines where canonical_sku is not null group by 1
        ), ranked as (
            select rev, row_number() over (order by rev desc) as rk, count(*) over () as n from by_sku
        )
        select
            (select sum(rev) filter (where rk <= round(0.2 * n)) / sum(rev) from ranked),
            (select sum(quantity_fulfilled) / sum(quantity) from revenue_lines),
            (select count(*) filter (where quantity_fulfilled < quantity) from revenue_lines)
    """).fetchone()
    print(f"\nTop 20% of SKUs share of revenue: {top20:.1%}")
    print(
        f"Unit fill rate (fulfilled / ordered): {fill_rate:.1%}; lines short-filled: {a_unfilled:,}"
    )

    dead, dead_value_share = con.execute(f"""
        with balances as (
            select sku, sum(quantity) as on_hand from {table("inventory_movements")} group by 1
        ), last_sale as (
            select sku, max(movement_ts) as last_sale
            from {table("inventory_movements")} where movement_type = 'sale' group by 1
        ), as_of as (select max(movement_ts) as ts from {table("inventory_movements")})
        select
            count(*) filter (where b.on_hand > 0 and (s.last_sale is null or s.last_sale < as_of.ts - interval 180 day)),
            sum(b.on_hand * p.unit_cost_usd) filter (where b.on_hand > 0 and (s.last_sale is null or s.last_sale < as_of.ts - interval 180 day))
                / sum(b.on_hand * p.unit_cost_usd)
        from balances b
        cross join as_of
        left join last_sale s using (sku)
        join products p using (sku)
    """).fetchone()
    print(
        f"Dead-stock SKUs (on hand, no sale in 180 days): {dead}; share of inventory cost: {dead_value_share:.1%}"
    )

    late_rate = con.execute(f"""
        with po as (
            select * from {table("purchase_orders")}
            qualify row_number() over (partition by po_id order by updated_at desc) = 1
        )
        select avg(case when actual_arrival_date > strptime(expected_arrival_date, ['%Y-%m-%d', '%m/%d/%Y'])::date + 3
                   then 1.0 else 0.0 end)
        from po where actual_arrival_date is not null
    """).fetchone()[0]
    print(f"Received POs arriving > 3 days after the quoted date: {late_rate:.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output-root", default=".")
    summarize(Path(parser.parse_args().output_root))


if __name__ == "__main__":
    main()
