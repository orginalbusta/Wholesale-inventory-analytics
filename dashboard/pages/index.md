---
title: Craftstones Inventory & Reorder Dashboard
---

<Alert status="warning">
<b>Synthetic data</b> · an ideal-state design, <b>not</b> the production system at Craftstones USA. No real customers, suppliers, prices or volumes appear here.
</Alert>

```sql kpis
with health as (
    select
        sum(on_hand_value_usd) as inventory_value_usd,
        sum(case when is_dead_stock then on_hand_value_usd else 0 end) as dead_stock_value_usd,
        count(*) filter (where is_dead_stock) as dead_stock_skus,
        max(as_of_date) as as_of_date
    from marts.inventory_health
),
reorder as (
    select
        count(*) filter (where abc_class = 'A') as a_skus,
        count(*) filter (where abc_class = 'A' and reorder_now) as a_skus_to_reorder
    from marts.reorder_recommendations
),
sales as (
    select
        sum(net_revenue_usd) as revenue_12m_usd,
        sum(gross_margin_usd) / sum(net_revenue_usd) as gross_margin_pct_12m,
        sum(unfilled_revenue_usd) as unfilled_revenue_12m_usd
    from marts.sales_monthly
    where month_start_date > (select max(month_start_date) from marts.sales_monthly) - interval 12 month
)
select
    *,
    dead_stock_value_usd / inventory_value_usd as dead_stock_share,
    a_skus_to_reorder::double / a_skus as a_skus_to_reorder_share
from health, reorder, sales
```

Data as of <Value data={kpis} column=as_of_date fmt="mmm d, yyyy" />. The question this dashboard answers: **which SKUs should we reorder, when, and how much, and where is cash tied up in dead stock?**

<BigValue data={kpis} value=revenue_12m_usd title="Net revenue, last 12 months" fmt=usd1m />
<BigValue data={kpis} value=gross_margin_pct_12m title="Gross margin, last 12 months" fmt=pct1 />
<BigValue data={kpis} value=inventory_value_usd title="Inventory value (at cost)" fmt=usd0k />
<BigValue data={kpis} value=dead_stock_value_usd title="Dead stock (no sale in 180 days)" fmt=usd0k />
<BigValue data={kpis} value=dead_stock_share title="Dead stock, share of inventory" fmt=pct1 />
<BigValue data={kpis} value=a_skus_to_reorder title="A-class SKUs at or below reorder point" />
<BigValue data={kpis} value=a_skus_to_reorder_share title="Share of active A-class SKUs to reorder" fmt=pct0 />

## Revenue and margin by month

```sql monthly
select month_start_date, 'Net revenue' as measure, sum(net_revenue_usd) as usd
from marts.sales_monthly group by 1
union all
select month_start_date, 'Gross margin', sum(gross_margin_usd)
from marts.sales_monthly group by 1
union all
select month_start_date, 'Revenue lost to stockouts', sum(unfilled_revenue_usd)
from marts.sales_monthly group by 1
order by 1, 2
```

<LineChart
    data={monthly}
    x=month_start_date
    y=usd
    series=measure
    yFmt=usd0k
    yAxisTitle=false
    title="Net revenue, gross margin, and revenue lost to stockouts"
>
    <ReferenceArea data={gem_shows} xMin=start_date xMax=end_date label=show_label color=info />
</LineChart>

```sql gem_shows
-- Short labels ("Tucson", "Denver"): the full show names overlap on a 3-year axis.
select start_date, end_date, split_part(show_name, ' ', 1) as show_label
from marts.gem_shows
```

Shaded bands are gem shows (Tucson in Jan-Feb, Denver in September). *Unfilled revenue* is demand that went unshipped because stock ran out: the cost of the simulated "gut feel" purchasing policy.

## Inventory value over time

```sql inventory_value
select
    date_day,
    sum(on_hand_value_usd) as on_hand_value_usd
from marts.inventory_value_daily
group by 1
order by 1
```

<AreaChart data={inventory_value} x=date_day y=on_hand_value_usd yFmt=usd0k title="Stock on hand, valued at cost" />

## Pages

- [Reorder](/reorder): what to order now, and how much
- [Inventory health](/inventory-health): ABC/XYZ classes, dead stock, days of supply
- [Suppliers](/suppliers): on-time rates and quoted vs. actual lead times
- [Sales & customers](/sales-and-customers): monthly trend by category and RFM segments

Built with dbt, DuckDB and Evidence. [dbt docs and lineage](https://orginalbusta.github.io/Wholesale-inventory-analytics/dbt-docs/) are published alongside this dashboard.
