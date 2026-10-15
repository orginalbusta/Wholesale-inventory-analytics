-- Grain: one row per order line whose SKU matches no product (planted issue 9).
-- Quarantined here so they never inflate revenue or demand, and so someone can fix them.

with

lines as (

    select * from {{ ref('stg_erp__sales_order_lines') }}

),

products as (

    select sku from {{ ref('stg_erp__products') }}

),

orders as (

    select * from {{ ref('stg_erp__sales_orders') }}

)

select
    lines.order_line_id,
    lines.order_id,
    orders.order_date,
    orders.customer_id,
    lines.sku_raw,
    lines.sku as sku_normalized,
    lines.quantity,
    lines.quantity_fulfilled,
    lines.unit_price_usd

from lines
left join products
    on lines.sku = products.sku
left join orders
    on lines.order_id = orders.order_id
where products.sku is null
