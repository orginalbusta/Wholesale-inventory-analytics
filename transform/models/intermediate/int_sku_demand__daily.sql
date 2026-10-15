-- Grain: one row per SKU per day, zero-filled from the SKU's launch (or the start of the
-- data) to the as-of date.
--
-- ordered_qty is TRUE demand: what customers asked for, including quantity that went
-- unfilled because stock ran out, and orders cancelled because nothing could ship
-- (cancel_reason = 'out_of_stock'). Customer-requested cancellations are not demand.
-- Forecasts must train on this, not on fulfilled (censored) sales; see
-- docs/06_future_ds_layer.md.

with

lines as (

    select * from {{ ref('stg_erp__sales_order_lines') }}
    where not is_return_line

),

orders as (

    select * from {{ ref('stg_erp__sales_orders') }}
    where coalesce(cancel_reason, '') <> 'customer_request'

),

products as (

    select * from {{ ref('stg_erp__products') }}

),

days as (

    select date_day from {{ ref('int_calendar__days') }}

),

line_demand as (

    select
        lines.sku,
        orders.order_date as date_day,
        orders.channel,
        lines.quantity,
        lines.quantity_fulfilled,
        (lines.quantity - lines.quantity_fulfilled)
        * lines.unit_price_usd
        * (1 - lines.line_discount_rate)
        * (1 - orders.order_discount_rate) as unfilled_revenue_usd

    from lines
    inner join orders
        on lines.order_id = orders.order_id

),

daily as (

    select
        sku,
        date_day,
        sum(quantity) as ordered_qty,
        sum(quantity_fulfilled) as fulfilled_qty,
        sum(case when channel = 'gem_show' then quantity else 0 end) as ordered_qty_gem_show,
        sum(unfilled_revenue_usd) as unfilled_revenue_usd,
        count(*) as n_order_lines

    from line_demand
    group by sku, date_day

),

spine as (

    select
        products.sku,
        days.date_day
    from products
    inner join days
        on products.launch_date <= days.date_day

),

filled as (

    select
        spine.sku,
        spine.date_day,
        coalesce(daily.ordered_qty, 0) as ordered_qty,
        coalesce(daily.fulfilled_qty, 0) as fulfilled_qty,
        coalesce(daily.ordered_qty, 0) - coalesce(daily.fulfilled_qty, 0) as unfilled_qty,
        coalesce(daily.ordered_qty_gem_show, 0) as ordered_qty_gem_show,
        coalesce(daily.unfilled_revenue_usd, 0) as unfilled_revenue_usd,
        coalesce(daily.n_order_lines, 0) as n_order_lines

    from spine
    left join daily
        on spine.sku = daily.sku and spine.date_day = daily.date_day

)

select * from filled
