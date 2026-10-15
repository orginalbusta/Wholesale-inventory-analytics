-- Grain: one row per purchase order line.
-- Converts local-currency cost to USD with the FX rate in effect on the order date, and
-- measures supplier performance: quoted vs. actual lead time, lateness, and fill rate.

with

po_lines as (

    select * from {{ ref('stg_erp__purchase_order_lines') }}

),

pos as (

    select * from {{ ref('stg_erp__purchase_orders') }}

),

fx as (

    select * from {{ ref('int_fx_rates__daily') }}

),

joined as (

    select
        po_lines.po_line_id,
        po_lines.po_id,
        pos.supplier_id,
        po_lines.sku,
        pos.order_date,
        pos.expected_arrival_date,
        pos.actual_arrival_date,
        pos.po_status,
        pos.currency,
        po_lines.quantity_ordered,
        po_lines.quantity_received,
        po_lines.unit_cost_local,
        po_lines.unit_cost_local / fx.units_per_usd as unit_cost_usd,
        pos.po_status in ('received', 'partially_received') as is_received,
        pos.po_status in ('open', 'in_transit') as is_open,
        (pos.expected_arrival_date - pos.order_date) as quoted_lead_time_days,
        case
            when pos.actual_arrival_date is not null
                then (pos.actual_arrival_date - pos.order_date)
        end as actual_lead_time_days

    from po_lines
    inner join pos
        on po_lines.po_id = pos.po_id
    left join fx
        on pos.currency = fx.currency and pos.order_date = fx.date_day

),

final as (

    select
        *,
        quantity_ordered * unit_cost_usd as ordered_value_usd,
        case when is_open then quantity_ordered else 0 end as open_quantity,
        actual_lead_time_days - quoted_lead_time_days as days_late,
        case
            when is_received
                then
                    actual_lead_time_days
                    <= quoted_lead_time_days + {{ var('on_time_grace_days') }}
        end as is_on_time,
        case when is_received then quantity_received / quantity_ordered end as fill_rate

    from joined

)

select * from final
