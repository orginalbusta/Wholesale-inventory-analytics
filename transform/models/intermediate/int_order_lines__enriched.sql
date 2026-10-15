-- Grain: one row per order line on a non-cancelled order with a known SKU.
-- Joins the order header, the canonical customer (issue 1), product attributes and the
-- unit cost in effect on the order date, then computes revenue, COGS and margin.
--
-- Sign convention: return lines (issue 6) carry negative revenue and COGS (a refund and
-- stock back on the shelf). Whole orders with status `returned` are refunded, so their
-- lines carry zero revenue and COGS but keep their quantities for fulfillment metrics.
-- Lines with unknown SKUs are excluded here and quarantined in int_order_lines__orphans.

with

lines as (

    select * from {{ ref('stg_erp__sales_order_lines') }}

),

orders as (

    select * from {{ ref('stg_erp__sales_orders') }}
    where order_status <> 'cancelled'

),

customers as (

    select
        dedup.customer_id,
        dedup.canonical_customer_id,
        canonical.customer_type
    from {{ ref('int_customers__deduplicated') }} as dedup
    inner join {{ ref('stg_erp__customers') }} as canonical
        on dedup.canonical_customer_id = canonical.customer_id

),

products as (

    select * from {{ ref('stg_erp__products') }}

),

costs as (

    select * from {{ ref('int_product_costs__history') }}

),

joined as (

    select
        lines.order_line_id,
        lines.order_id,
        lines.line_no,
        orders.order_date,
        orders.order_status,
        orders.channel,
        orders.warehouse_id,
        orders.customer_id,
        customers.canonical_customer_id,
        customers.customer_type,
        orders.sales_rep_id,
        lines.sku,
        products.category,
        products.product_name,
        lines.is_return_line,
        orders.order_status = 'returned' as is_returned_order,
        lines.quantity,
        lines.quantity_fulfilled,
        lines.unit_price_usd,
        lines.line_discount_rate,
        orders.order_discount_rate,
        costs.unit_cost_usd,
        orders.updated_at as order_updated_at

    from lines
    inner join orders
        on lines.order_id = orders.order_id
    inner join products
        on lines.sku = products.sku
    inner join customers
        on orders.customer_id = customers.customer_id
    left join costs
        on
            lines.sku = costs.sku
            and orders.order_date >= costs.valid_from
            and orders.order_date < costs.valid_to

),

measured as (

    select
        *,
        case
            when is_return_line then -1
            when is_returned_order then 0
            else 1
        end as revenue_sign,
        case when is_return_line then 0 else quantity end as quantity_ordered,
        case when is_return_line then 0 else quantity - quantity_fulfilled end as quantity_unfilled,
        unit_price_usd * (1 - line_discount_rate) * (1 - order_discount_rate) as net_unit_price_usd

    from joined

),

final as (

    select
        order_line_id,
        order_id,
        line_no,
        order_date,
        order_status,
        channel,
        warehouse_id,
        customer_id,
        canonical_customer_id,
        customer_type,
        sales_rep_id,
        sku,
        category,
        product_name,
        is_return_line,
        is_returned_order,
        quantity_ordered,
        case when is_return_line then 0 else quantity_fulfilled end as quantity_fulfilled,
        case when is_return_line then quantity_fulfilled else 0 end as quantity_returned,
        quantity_unfilled,
        unit_price_usd,
        line_discount_rate,
        order_discount_rate,
        unit_cost_usd,
        revenue_sign * quantity_fulfilled * unit_price_usd as gross_revenue_usd,
        revenue_sign * quantity_fulfilled * net_unit_price_usd as net_revenue_usd,
        revenue_sign * quantity_fulfilled * unit_cost_usd as cogs_usd,
        revenue_sign
        * quantity_fulfilled
        * (net_unit_price_usd - unit_cost_usd) as gross_margin_usd,
        quantity_unfilled * net_unit_price_usd as unfilled_revenue_usd,
        order_updated_at

    from measured

)

select * from final
