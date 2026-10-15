-- Grain: one row per month x category x channel x customer type.
-- Revenue is net of discounts and refunds; unfilled revenue is demand lost to stockouts on
-- orders that still shipped (fully cancelled stockout orders are in mart_stockouts).

with

lines as (

    select * from {{ ref('fct_order_lines') }}

),

monthly as (

    select
        cast({{ dbt.date_trunc('month', 'order_date') }} as date) as month_start_date,
        category,
        channel,
        customer_type,
        count(distinct order_id) as order_count,
        count(distinct canonical_customer_id) as customer_count,
        sum(quantity_fulfilled) - sum(quantity_returned) as units_net,
        sum(gross_revenue_usd) as gross_revenue_usd,
        sum(net_revenue_usd) as net_revenue_usd,
        sum(cogs_usd) as cogs_usd,
        sum(gross_margin_usd) as gross_margin_usd,
        sum(unfilled_revenue_usd) as unfilled_revenue_usd

    from lines
    group by 1, 2, 3, 4

)

select
    cast(month_start_date as date) as month_start_date,
    cast(category as varchar) as category,
    cast(channel as varchar) as channel,
    cast(customer_type as varchar) as customer_type,
    cast(order_count as bigint) as order_count,
    cast(customer_count as bigint) as customer_count,
    cast(units_net as double) as units_net,
    cast(gross_revenue_usd as double) as gross_revenue_usd,
    cast(net_revenue_usd as double) as net_revenue_usd,
    cast(cogs_usd as double) as cogs_usd,
    cast(gross_margin_usd as double) as gross_margin_usd,
    cast(gross_margin_usd / nullif(net_revenue_usd, 0) as double) as gross_margin_pct,
    cast(unfilled_revenue_usd as double) as unfilled_revenue_usd

from monthly
