---
title: Sales & customers
---

<Alert status="warning">
<b>Synthetic data</b> · an ideal-state design, <b>not</b> the production system at Craftstones USA. Customer names are fictional.
</Alert>

## Revenue by category

```sql by_category
select
    month_start_date,
    category,
    sum(net_revenue_usd) as net_revenue_usd
from marts.sales_monthly
group by 1, 2
order by 1, 2
```

```sql gem_shows
-- Short labels ("Tucson", "Denver"): the full show names overlap on a 3-year axis.
select start_date, end_date, split_part(show_name, ' ', 1) as show_label
from marts.gem_shows
```

<BarChart data={by_category} x=month_start_date y=net_revenue_usd series=category type=stacked yFmt=usd0k title="Net revenue by month and category">
    <ReferenceArea data={gem_shows} xMin=start_date xMax=end_date label=show_label color=info />
</BarChart>

Jewelry components and crystal clusters peak before the holidays; decor and landscape stone peaks in spring; everything dips in July. Shaded bands are gem shows.

## Channel and customer mix

```sql by_channel
select channel, sum(net_revenue_usd) as net_revenue_usd, sum(order_count) as orders
from marts.sales_monthly
group by 1
order by 2 desc
```

```sql by_customer_type
select
    customer_type,
    sum(net_revenue_usd) as net_revenue_usd,
    sum(gross_margin_usd) / sum(net_revenue_usd) as gross_margin_pct
from marts.sales_monthly
group by 1
order by 2 desc
```

<BarChart data={by_channel} x=channel y=net_revenue_usd yFmt=usd0k title="Revenue by channel" />
<BarChart data={by_customer_type} x=customer_type y=net_revenue_usd yFmt=usd0k swapXY=true title="Revenue by customer type" />

## Customer segments (RFM)

Customers are scored 1-5 on **R**ecency, **F**requency (orders in the last 12 months) and **M**onetary value (revenue in the last 12 months). Duplicate customer records for the same business are merged first.

```sql segments
select
    segment,
    count(*) as customers,
    sum(monetary_12m_usd) as revenue_12m_usd
from marts.customer_rfm
group by 1
order by 3 desc
```

<BarChart data={segments} x=segment y=customers title="Customers by segment" />
<BarChart data={segments} x=segment y=revenue_12m_usd yFmt=usd0k title="Last-12-month revenue by segment" />

```sql at_risk
select customer_name, customer_type, state, last_order_date, recency_days, frequency_12m, monetary_12m_usd
from marts.customer_rfm
where segment = 'At Risk'
order by monetary_12m_usd desc
```

**At Risk**: customers who used to order often but have gone quiet. A sales rep's call list.

<DataTable data={at_risk} rows=10>
    <Column id=customer_name title="Customer" />
    <Column id=customer_type title="Type" />
    <Column id=state />
    <Column id=last_order_date title="Last order" />
    <Column id=recency_days title="Days since" fmt=num0 />
    <Column id=frequency_12m title="Orders (12m)" />
    <Column id=monetary_12m_usd title="Revenue (12m)" fmt=usd0 />
</DataTable>
