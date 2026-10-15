-- Grain: one row per supplier, over all purchase orders.
-- On time = arrived no later than the quoted date plus `on_time_grace_days`.
-- quoted_vs_actual_gap_days > 0 means the supplier's quoted lead time is optimistic.

with

purchase_orders as (

    select
        supplier_id,
        po_id,
        min(order_date) as order_date,
        sum(ordered_value_usd) as ordered_value_usd,
        sum(quantity_ordered) as quantity_ordered,
        sum(quantity_received) as quantity_received,
        max(case when is_received then 1 else 0 end) = 1 as is_received,
        min(case when is_on_time then 1 else 0 end) = 1 as is_on_time,
        max(quoted_lead_time_days) as quoted_lead_time_days,
        max(actual_lead_time_days) as actual_lead_time_days,
        max(case when quantity_received < quantity_ordered then 1 else 0 end) = 1 as is_short
    from {{ ref('fct_purchase_order_lines') }}
    group by supplier_id, po_id

),

performance as (

    select
        supplier_id,
        {{ supplier_performance_metrics() }}
    from purchase_orders
    group by supplier_id

),

suppliers as (

    select * from {{ ref('dim_suppliers') }}

)

select
    cast(suppliers.supplier_id as varchar) as supplier_id,
    cast(suppliers.supplier_name as varchar) as supplier_name,
    cast(suppliers.country as varchar) as country,
    cast(suppliers.currency as varchar) as currency,
    cast(coalesce(performance.po_count, 0) as bigint) as po_count,
    cast(coalesce(performance.received_po_count, 0) as bigint) as received_po_count,
    cast(coalesce(performance.spend_usd, 0) as double) as spend_usd,
    cast(performance.on_time_rate as double) as on_time_rate,
    cast(performance.lead_time_mean_days as double) as lead_time_mean_days,
    cast(performance.lead_time_std_days as double) as lead_time_std_days,
    cast(performance.quoted_lead_time_mean_days as double) as quoted_lead_time_mean_days,
    cast(performance.quoted_vs_actual_gap_days as double) as quoted_vs_actual_gap_days,
    cast(performance.fill_rate as double) as fill_rate,
    cast(coalesce(performance.short_shipment_count, 0) as bigint) as short_shipment_count

from suppliers
left join performance
    on suppliers.supplier_id = performance.supplier_id
