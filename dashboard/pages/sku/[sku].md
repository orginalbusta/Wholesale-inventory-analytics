---
title: SKU detail
---

<Alert status="warning">
<b>Synthetic data</b> · an ideal-state design, <b>not</b> the production system at Craftstones USA.
</Alert>

```sql sku_info
-- Every launched SKU has a page; reorder fields are empty for discontinued SKUs.
select
    h.sku,
    h.product_name,
    h.category,
    h.supplier_id,
    s.supplier_name,
    h.abc_class || h.xyz_class as class,
    h.is_active,
    r.target_service_level,
    h.on_hand_qty,
    h.on_order_qty,
    r.reorder_point_qty,
    r.safety_stock_qty,
    r.reorder_now,
    r.suggested_order_qty,
    r.lead_time_mean_days,
    r.lead_time_std_days,
    r.lead_time_source,
    h.days_of_supply,
    h.days_since_last_sale,
    h.is_dead_stock,
    h.as_of_date,
    -- Chart range that always shows the reorder point line as well as the stock history.
    1.1 * greatest(
        coalesce(r.reorder_point_qty, 0),
        coalesce((select max(i.on_hand_qty) from marts.sku_inventory_daily as i where i.sku = h.sku), 0),
        1
    ) as stock_chart_max,
    case
        when r.sku is null then 'Discontinued: not reordered'
        when r.reorder_now
            then 'Reorder ' || format('{:,}', cast(r.suggested_order_qty as bigint)) || ' units now'
        else 'No order needed today'
    end as recommendation
from marts.inventory_health as h
left join marts.reorder_recommendations as r using (sku)
left join marts.supplier_performance as s on h.supplier_id = s.supplier_id
where h.sku = '${params.sku}'
```

{#if sku_info.length > 0}

# {sku_info[0].sku}: {sku_info[0].product_name}

{sku_info[0].category} · supplier **{sku_info[0].supplier_name}** · class **{sku_info[0].class}** {#if sku_info[0].is_active}(target service level <Value data={sku_info} column=target_service_level fmt=pct0 />){:else} · discontinued{/if} · data as of <Value data={sku_info} column=as_of_date fmt="mmm d, yyyy" />

<BigValue data={sku_info} value=recommendation title="Recommendation" />
<BigValue data={sku_info} value=on_hand_qty title="On hand" fmt=num0 />
<BigValue data={sku_info} value=on_order_qty title="On order" fmt=num0 />
<BigValue data={sku_info} value=reorder_point_qty title="Reorder point" fmt=num0 />
<BigValue data={sku_info} value=safety_stock_qty title="Safety stock" fmt=num0 />
<BigValue data={sku_info} value=days_of_supply title="Days of supply" fmt=num0 />

```sql stock_history
select date_day, on_hand_qty
from marts.sku_inventory_daily
where sku = '${params.sku}'
order by date_day
```

<LineChart data={stock_history} x=date_day y=on_hand_qty yFmt=num0 title="Stock on hand, last 12 months (all warehouses)" yMax={sku_info[0].stock_chart_max} emptySet=pass emptyMessage="No stock history in the last 12 months.">
    <ReferenceLine y={sku_info[0].reorder_point_qty} label="Reorder point" />
    <ReferenceLine y={sku_info[0].safety_stock_qty} label="Safety stock" />
</LineChart>

```sql demand_weekly
select week_start_date, 'Fulfilled' as demand_type, fulfilled_qty as qty
from marts.sku_demand_weekly
where sku = '${params.sku}'
union all
select week_start_date, 'Lost to stockouts' as demand_type, unfilled_qty as qty
from marts.sku_demand_weekly
where sku = '${params.sku}'
order by week_start_date, demand_type
```

<BarChart data={demand_weekly} x=week_start_date y=qty series=demand_type yFmt=num0 title="Weekly demand, last 12 months" emptySet=pass emptyMessage="No demand in the last 12 months." />

```sql stockouts
select month_start_date, stockout_days, unfilled_qty, unfilled_revenue_estimate_usd
from marts.stockouts
where sku = '${params.sku}'
    and month_start_date > (select max(month_start_date) from marts.stockouts) - interval 12 month
order by month_start_date
```

<BarChart data={stockouts} x=month_start_date y=stockout_days yFmt=num0 title="Stockout days per month" emptySet=pass emptyMessage="No stockouts in the last 12 months." />

## Purchase orders

```sql purchase_orders
select
    po_id,
    order_date,
    expected_arrival_date,
    strftime(actual_arrival_date, '%Y-%m-%d') as actual_arrival_date,
    po_status,
    quantity_ordered,
    open_quantity,
    quoted_lead_time_days,
    actual_lead_time_days,
    days_late
from marts.sku_purchase_orders
where sku = '${params.sku}'
order by order_date desc
```

Open orders and the last 12 months. Lead times used for the reorder point: mean <Value data={sku_info} column=lead_time_mean_days fmt=num1 /> days, standard deviation <Value data={sku_info} column=lead_time_std_days fmt=num1 /> days (<Value data={sku_info} column=lead_time_source />).

<DataTable data={purchase_orders} rows=10 emptySet=pass emptyMessage="No purchase orders in the last 12 months.">
    <Column id=po_id title="PO" />
    <Column id=order_date title="Ordered" />
    <Column id=expected_arrival_date title="Expected" />
    <Column id=actual_arrival_date title="Arrived" />
    <Column id=po_status title="Status" />
    <Column id=quantity_ordered title="Qty" fmt=num0 />
    <Column id=open_quantity title="Open qty" fmt=num0 />
    <Column id=quoted_lead_time_days title="Quoted lead time" fmt=num0 />
    <Column id=actual_lead_time_days title="Actual lead time" fmt=num0 />
    <Column id=days_late title="Days late" fmt=num0 contentType=delta downIsGood=true />
</DataTable>

## Supplier scorecard

```sql supplier
select
    supplier_name,
    country,
    on_time_rate,
    lead_time_mean_days,
    quoted_vs_actual_gap_days,
    fill_rate,
    po_count
from marts.supplier_performance
where supplier_id = '${sku_info[0].supplier_id}'
```

<BigValue data={supplier} value=on_time_rate title="On-time rate" fmt=pct0 />
<BigValue data={supplier} value=lead_time_mean_days title="Mean lead time (days)" fmt=num1 />
<BigValue data={supplier} value=quoted_vs_actual_gap_days title="Actual minus quoted (days)" fmt=num1 />
<BigValue data={supplier} value=fill_rate title="Fill rate" fmt=pct0 />

[All SKUs](/sku) · [Reorder recommendations](/reorder) · [What-if reorder policy](/what-if) · [Suppliers](/suppliers)

{:else}

# SKU not found

No SKU called **{params.sku}**. See [all SKUs](/sku).

{/if}
