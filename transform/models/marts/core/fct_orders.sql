-- Grain: one row per sales order (all statuses). Money and quantities are summed from
-- fct_order_lines, so cancelled orders show zero (a singular test reconciles the two).

with

orders as (

    select * from {{ ref('stg_erp__sales_orders') }}

),

dedup as (

    select * from {{ ref('int_customers__deduplicated') }}

),

line_totals as (

    select
        order_id,
        count(*) as n_lines,
        sum(quantity_ordered) as quantity_ordered,
        sum(quantity_fulfilled) as quantity_fulfilled,
        sum(quantity_unfilled) as quantity_unfilled,
        sum(net_revenue_usd) as net_revenue_usd,
        sum(cogs_usd) as cogs_usd,
        sum(gross_margin_usd) as gross_margin_usd,
        sum(unfilled_revenue_usd) as unfilled_revenue_usd
    from {{ ref('fct_order_lines') }}
    group by order_id

)

select
    cast(orders.order_id as varchar) as order_id,
    cast(orders.order_date as date) as order_date,
    cast(orders.customer_id as varchar) as customer_id,
    cast(dedup.canonical_customer_id as varchar) as canonical_customer_id,
    cast(orders.channel as varchar) as channel,
    cast(orders.warehouse_id as varchar) as warehouse_id,
    cast(orders.order_status as varchar) as order_status,
    cast(orders.cancel_reason as varchar) as cancel_reason,
    cast(orders.ship_date as date) as ship_date,
    cast(orders.sales_rep_id as varchar) as sales_rep_id,
    cast(orders.order_discount_rate as double) as order_discount_rate,
    cast(coalesce(line_totals.n_lines, 0) as bigint) as n_lines,
    cast(coalesce(line_totals.quantity_ordered, 0) as double) as quantity_ordered,
    cast(coalesce(line_totals.quantity_fulfilled, 0) as double) as quantity_fulfilled,
    cast(coalesce(line_totals.quantity_unfilled, 0) as double) as quantity_unfilled,
    cast(coalesce(line_totals.net_revenue_usd, 0) as double) as net_revenue_usd,
    cast(coalesce(line_totals.cogs_usd, 0) as double) as cogs_usd,
    cast(coalesce(line_totals.gross_margin_usd, 0) as double) as gross_margin_usd,
    cast(coalesce(line_totals.unfilled_revenue_usd, 0) as double) as unfilled_revenue_usd,
    cast(orders.updated_at as timestamp) as updated_at

from orders
left join dedup
    on orders.customer_id = dedup.customer_id
left join line_totals
    on orders.order_id = line_totals.order_id
