-- Order totals in fct_orders must equal the sum of their lines in fct_order_lines (within a cent).

with

line_totals as (

    select
        order_id,
        sum(net_revenue_usd) as net_revenue_usd
    from {{ ref('fct_order_lines') }}
    group by order_id

)

select
    orders.order_id,
    orders.net_revenue_usd as order_revenue_usd,
    coalesce(line_totals.net_revenue_usd, 0) as line_revenue_usd
from {{ ref('fct_orders') }} as orders
left join line_totals
    on orders.order_id = line_totals.order_id
where abs(orders.net_revenue_usd - coalesce(line_totals.net_revenue_usd, 0)) > 0.01
