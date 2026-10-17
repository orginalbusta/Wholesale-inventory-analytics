---
title: SKU detail
---

<script>
    // The SKU comes from the address: /sku/detail/?id=AGT-DEC-0017. This page is built once,
    // without an id, so it exists as a real file (HTTP 200). The id is read only after the page
    // mounts in the browser; changing it then re-runs every query below (reading it earlier
    // would reuse the empty results built ahead of time). Only letters, digits and dashes are kept.
    // `$page` and `onMount` are already imported by Evidence's generated page code.
    let mounted = false;
    onMount(() => (mounted = true));
    $: sku_id = mounted ? ($page.url.searchParams.get('id') ?? '').replace(/[^A-Za-z0-9-]/g, '') : '';
</script>

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
    strftime(h.as_of_date, '%b %-d, %Y') as as_of_label,
    printf('%d%%', cast(round(r.target_service_level * 100) as integer)) as service_level_label,
    printf('%.1f', r.lead_time_mean_days) as lead_time_mean_label,
    printf('%.1f', r.lead_time_std_days) as lead_time_std_label,
    case r.lead_time_source
        when 'actual_trailing_12m' then 'actual deliveries, last 12 months'
        when 'actual_all_history' then 'all actual deliveries'
        when 'quoted' then 'the supplier quote; no deliveries yet'
        else r.lead_time_source
    end as lead_time_source_label,
    -- Chart range that always shows the reorder point line as well as the stock history.
    -- rounded up to two significant digits, so the top tick is a round number
    ceil(stock_peak / pow(10, floor(log10(stock_peak)) - 1)) * pow(10, floor(log10(stock_peak)) - 1)
        as stock_chart_max,
    case
        when r.sku is null then 'Discontinued: not reordered'
        when r.reorder_now
            then 'Reorder ' || format('{:,}', cast(r.suggested_order_qty as bigint)) || ' units now'
        else 'No order needed today'
    end as recommendation
from (
    select
        *,
        1.05 * greatest(
            coalesce(r0.reorder_point_qty, 0),
            coalesce((select max(i.on_hand_qty) from marts.sku_inventory_daily as i where i.sku = h0.sku), 0),
            10
        ) as stock_peak
    from marts.inventory_health as h0
    left join (select sku as r_sku, reorder_point_qty from marts.reorder_recommendations) as r0
        on h0.sku = r0.r_sku
) as h
left join marts.reorder_recommendations as r using (sku)
left join marts.supplier_performance as s on h.supplier_id = s.supplier_id
where h.sku = '${sku_id}'
```

{#if !mounted}

Loading SKU...

{:else if !sku_id}

# Pick a SKU

Open one from [all SKUs](/sku), or from the [reorder](/reorder), [inventory health](/inventory-health) or [what-if](/what-if) tables.

{:else if !sku_info.dataLoaded}

Loading {sku_id}...

{:else if sku_info.length > 0}

# {sku_info[0].sku}: {sku_info[0].product_name}

{sku_info[0].category} · supplier **{sku_info[0].supplier_name}** · class **{sku_info[0].class}**{#if sku_info[0].is_active}, target service level {sku_info[0].service_level_label}{:else} · discontinued{/if} · data as of {sku_info[0].as_of_label}

<BigValue data={sku_info} value=recommendation title="Recommendation" />
<BigValue data={sku_info} value=on_hand_qty title="On hand" fmt=num0 />
<BigValue data={sku_info} value=on_order_qty title="On order" fmt=num0 />
<BigValue data={sku_info} value=reorder_point_qty title="Reorder point" fmt=num0 />
<BigValue data={sku_info} value=safety_stock_qty title="Safety stock" fmt=num0 />
<BigValue data={sku_info} value=days_of_supply title="Days of supply" fmt=num0 />

```sql stock_history
select date_day, on_hand_qty
from marts.sku_inventory_daily
where sku = '${sku_id}'
order by date_day
```

<LineChart data={stock_history} x=date_day y=on_hand_qty yFmt=num0 title="Stock on hand, last 12 months (all warehouses)" yMax={sku_info[0].stock_chart_max} emptySet=pass emptyMessage="No stock history in the last 12 months.">
    <ReferenceLine y={sku_info[0].reorder_point_qty} label="Reorder point" />
    <ReferenceLine y={sku_info[0].safety_stock_qty} label="Safety stock" />
</LineChart>

```sql demand_weekly
select week_start_date, 'Fulfilled' as demand_type, fulfilled_qty as qty
from marts.sku_demand_weekly
where sku = '${sku_id}'
union all
select week_start_date, 'Lost to stockouts' as demand_type, unfilled_qty as qty
from marts.sku_demand_weekly
where sku = '${sku_id}'
order by week_start_date, demand_type
```

<BarChart data={demand_weekly} x=week_start_date y=qty series=demand_type yFmt=num0 title="Weekly demand, last 12 months" emptySet=pass emptyMessage="No demand in the last 12 months." />

```sql stockouts
select month_start_date, stockout_days, unfilled_qty, unfilled_revenue_estimate_usd
from marts.stockouts
where sku = '${sku_id}'
    and month_start_date > (select max(month_start_date) from marts.stockouts) - interval 12 month
order by month_start_date
```

```sql stockout_axis
-- At least 0-5 on the axis, so small whole-day counts don't produce repeated ticks
select greatest(5, max(stockout_days)) as y_max from ${stockouts}
```

<BarChart data={stockouts} x=month_start_date y=stockout_days yFmt=num0 yMax={stockout_axis[0]?.y_max ?? 5} title="Stockout days per month" emptySet=pass emptyMessage="No stockouts in the last 12 months." />

## Purchase orders

```sql purchase_orders
select
    po_id,
    order_date,
    expected_arrival_date,
    strftime(actual_arrival_date, '%Y-%m-%d') as actual_arrival_date,
    replace(po_status, '_', ' ') as po_status,
    quantity_ordered,
    open_quantity,
    quoted_lead_time_days,
    actual_lead_time_days,
    days_late
from marts.sku_purchase_orders
where sku = '${sku_id}'
order by order_date desc
```

Open orders and the last 12 months.

{#if sku_info[0].is_active}

The reorder point uses a mean lead time of {sku_info[0].lead_time_mean_label} days with a standard deviation of {sku_info[0].lead_time_std_label} days, from {sku_info[0].lead_time_source_label}.

{/if}

<DataTable data={purchase_orders} rows=10 emptySet=pass emptyMessage="No purchase orders in the last 12 months.">
    <Column id=order_date title="Ordered" />
    <Column id=expected_arrival_date title="Expected" />
    <Column id=actual_arrival_date title="Arrived" />
    <Column id=po_status title="Status" />
    <Column id=quantity_ordered title="Qty" fmt=num0 />
    <Column id=quoted_lead_time_days title="Quoted days" fmt=num0 />
    <Column id=actual_lead_time_days title="Actual days" fmt=num0 />
    <Column id=days_late title="Days late" fmt=num0 />
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
where supplier_id = (select supplier_id from marts.inventory_health where sku = '${sku_id}')
```

{#if supplier.dataLoaded && supplier.length > 0}

<BigValue data={supplier} value=on_time_rate title="On-time rate" fmt=pct0 />
<BigValue data={supplier} value=lead_time_mean_days title="Mean lead time (days)" fmt=num1 />
<BigValue data={supplier} value=quoted_vs_actual_gap_days title="Actual minus quoted (days)" fmt=num1 />
<BigValue data={supplier} value=fill_rate title="Fill rate" fmt=pct0 />

{:else}

Loading the supplier scorecard...

{/if}

[All SKUs](/sku) · [Reorder recommendations](/reorder) · [What-if reorder policy](/what-if) · [Suppliers](/suppliers)

{:else}

# SKU not found

No SKU called **{sku_id}**. See [all SKUs](/sku).

{/if}
