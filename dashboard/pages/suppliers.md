---
title: Supplier performance
---

<Alert status="warning">
<b>Synthetic data</b> · an ideal-state design, <b>not</b> the production system at Craftstones USA. Supplier names are fictional.
</Alert>

On time = arrived no later than the supplier's quoted date plus 3 days' grace. Reorder points use each supplier's **actual** lead-time history, because quotes tend to be optimistic.

```sql suppliers
select
    supplier_name,
    country,
    po_count,
    spend_usd,
    on_time_rate,
    lead_time_mean_days,
    lead_time_std_days,
    quoted_lead_time_mean_days,
    quoted_vs_actual_gap_days,
    fill_rate,
    short_shipment_count
from marts.supplier_performance
where received_po_count > 0
order by on_time_rate
```

## Reliability: on-time rate vs. lead-time variability

<BubbleChart
    data={suppliers}
    x=lead_time_std_days
    y=on_time_rate
    size=spend_usd
    series=country
    yFmt=pct0
    xAxisTitle="Lead-time standard deviation (days)"
    yAxisTitle="On-time rate"
    tooltipTitle=supplier_name
/>

Bubbles are sized by spend. Suppliers in the bottom right are both late and unpredictable, so they need the most safety stock.

## Quoted vs. actual lead time

```sql lead_times
select supplier_name, 'Quoted' as measure, quoted_lead_time_mean_days as days from ${suppliers}
union all
select supplier_name, 'Actual', lead_time_mean_days from ${suppliers}
```

<BarChart data={lead_times} x=supplier_name y=days series=measure type=grouped swapXY=true title="Mean lead time in days" />

## On-time rate by quarter

```sql quarterly
select
    quarter_start_date,
    sum(on_time_rate * received_po_count) / sum(received_po_count) as on_time_rate,
    sum(spend_usd) as spend_usd
from marts.supplier_performance_quarterly
where received_po_count > 0
group by 1
order by 1
```

<LineChart data={quarterly} x=quarter_start_date y=on_time_rate yFmt=pct0 title="All suppliers, weighted by received POs" />

## Scorecard

<DataTable data={suppliers} rows=20>
    <Column id=supplier_name title="Supplier" />
    <Column id=country />
    <Column id=po_count title="POs" />
    <Column id=spend_usd title="Spend" fmt=usd0k />
    <Column id=on_time_rate title="On time" fmt=pct0 />
    <Column id=quoted_lead_time_mean_days title="Quoted (days)" fmt=num0 />
    <Column id=lead_time_mean_days title="Actual (days)" fmt=num0 />
    <Column id=lead_time_std_days title="Actual σ" fmt=num1 />
    <Column id=fill_rate title="Fill rate" fmt=pct0 />
    <Column id=short_shipment_count title="Short shipments" />
</DataTable>
