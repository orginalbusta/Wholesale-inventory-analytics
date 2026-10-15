-- Grain: one row per order line (non-cancelled orders, known SKUs).
-- Incremental: each run re-processes lines whose order changed within the lookback window
-- (late-arriving status updates, planted issue 5, and later return lines) and replaces them
-- by order_line_id. A full refresh gives the same result (tested).

{{
    config(
        materialized='incremental',
        unique_key='order_line_id',
        incremental_strategy='delete+insert',
        on_schema_change='fail',
    )
}}

with

lines as (

    select * from {{ ref('int_order_lines__enriched') }}

    {% if is_incremental() %}
        where order_updated_at > (
            select {{ dbt.dateadd('day', -var('incremental_lookback_days'), 'max(order_updated_at)') }}
            from {{ this }}
        )
    {% endif %}

)

select
    cast(order_line_id as varchar) as order_line_id,
    cast(order_id as varchar) as order_id,
    cast(line_no as integer) as line_no,
    cast(order_date as date) as order_date,
    cast(order_status as varchar) as order_status,
    cast(channel as varchar) as channel,
    cast(warehouse_id as varchar) as warehouse_id,
    cast(customer_id as varchar) as customer_id,
    cast(canonical_customer_id as varchar) as canonical_customer_id,
    cast(customer_type as varchar) as customer_type,
    cast(sales_rep_id as varchar) as sales_rep_id,
    cast(sku as varchar) as sku,
    cast(category as varchar) as category,
    cast(is_return_line as boolean) as is_return_line,
    cast(is_returned_order as boolean) as is_returned_order,
    cast(quantity_ordered as double) as quantity_ordered,
    cast(quantity_fulfilled as double) as quantity_fulfilled,
    cast(quantity_returned as double) as quantity_returned,
    cast(quantity_unfilled as double) as quantity_unfilled,
    cast(unit_price_usd as double) as unit_price_usd,
    cast(unit_cost_usd as double) as unit_cost_usd,
    cast(line_discount_rate as double) as line_discount_rate,
    cast(order_discount_rate as double) as order_discount_rate,
    cast(gross_revenue_usd as double) as gross_revenue_usd,
    cast(net_revenue_usd as double) as net_revenue_usd,
    cast(cogs_usd as double) as cogs_usd,
    cast(gross_margin_usd as double) as gross_margin_usd,
    cast(unfilled_revenue_usd as double) as unfilled_revenue_usd,
    cast(order_updated_at as timestamp) as order_updated_at,
    cast('{{ invocation_id }}' as varchar) as dbt_invocation_id

from lines
