-- Grain: one row per supplier per quarter (by PO order date), for trends.
-- Same metrics and definitions as mart_supplier_performance.

with

purchase_orders as (

    select
        supplier_id,
        po_id,
        cast({{ dbt.date_trunc('quarter', 'min(order_date)') }} as date) as quarter_start_date,
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
        quarter_start_date,
        {{ supplier_performance_metrics() }}
    from purchase_orders
    group by supplier_id, quarter_start_date

)

select
    cast(supplier_id as varchar) as supplier_id,
    cast(quarter_start_date as date) as quarter_start_date,
    cast(po_count as bigint) as po_count,
    cast(received_po_count as bigint) as received_po_count,
    cast(spend_usd as double) as spend_usd,
    cast(on_time_rate as double) as on_time_rate,
    cast(lead_time_mean_days as double) as lead_time_mean_days,
    cast(lead_time_std_days as double) as lead_time_std_days,
    cast(quoted_lead_time_mean_days as double) as quoted_lead_time_mean_days,
    cast(quoted_vs_actual_gap_days as double) as quoted_vs_actual_gap_days,
    cast(fill_rate as double) as fill_rate,
    cast(short_shipment_count as bigint) as short_shipment_count

from performance
