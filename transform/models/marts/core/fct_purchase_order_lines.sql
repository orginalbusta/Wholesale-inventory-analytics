-- Grain: one row per purchase order line, with USD cost, lead times, on-time flag and fill rate.

select
    cast(po_line_id as varchar) as po_line_id,
    cast(po_id as varchar) as po_id,
    cast(supplier_id as varchar) as supplier_id,
    cast(sku as varchar) as sku,
    cast(order_date as date) as order_date,
    cast(expected_arrival_date as date) as expected_arrival_date,
    cast(actual_arrival_date as date) as actual_arrival_date,
    cast(po_status as varchar) as po_status,
    cast(currency as varchar) as currency,
    cast(quantity_ordered as double) as quantity_ordered,
    cast(quantity_received as double) as quantity_received,
    cast(open_quantity as double) as open_quantity,
    cast(unit_cost_local as double) as unit_cost_local,
    cast(unit_cost_usd as double) as unit_cost_usd,
    cast(ordered_value_usd as double) as ordered_value_usd,
    cast(quoted_lead_time_days as integer) as quoted_lead_time_days,
    cast(actual_lead_time_days as integer) as actual_lead_time_days,
    cast(days_late as integer) as days_late,
    cast(is_received as boolean) as is_received,
    cast(is_on_time as boolean) as is_on_time,
    cast(fill_rate as double) as fill_rate

from {{ ref('int_purchase_order_lines__enriched') }}
