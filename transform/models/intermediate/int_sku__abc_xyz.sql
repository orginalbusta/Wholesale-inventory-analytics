-- Grain: one row per SKU.
-- ABC: rank SKUs by trailing-12-month net revenue. A = the top SKUs that make up the first
--      80% of revenue, B = the next 15%, C = the rest (thresholds are dbt vars). A SKU is A
--      when the revenue ranked ahead of it is still below 80%, so the SKU that crosses the
--      line counts as A.
-- XYZ: coefficient of variation of weekly demand (true demand, incl. unfilled) over the
--      trailing 26 weeks: X < 0.5, Y 0.5-1.0, Z > 1.0 (dbt vars). No demand at all = Z.
-- Lives in an intermediate model (not dim_products) so marts can use it without cycles.

{%- set abc = var('abc_thresholds') -%}
{%- set xyz = var('xyz_thresholds') %}

with

products as (

    select sku from {{ ref('stg_erp__products') }}

),

data_bounds as (

    select max(date_day) as as_of_date from {{ ref('int_calendar__days') }}

),

revenue as (

    select
        order_lines.sku,
        sum(order_lines.net_revenue_usd) as revenue_12m_usd
    from {{ ref('int_order_lines__enriched') }} as order_lines
    cross join data_bounds
    where order_lines.order_date > data_bounds.as_of_date - 365
    group by order_lines.sku

),

ranked as (

    select
        products.sku,
        greatest(coalesce(revenue.revenue_12m_usd, 0), 0) as revenue_12m_usd

    from products
    left join revenue
        on products.sku = revenue.sku

),

shares as (

    select
        sku,
        revenue_12m_usd,
        (
            sum(revenue_12m_usd) over (
                order by revenue_12m_usd desc, sku asc
                rows between unbounded preceding and current row
            ) - revenue_12m_usd
        ) / nullif(sum(revenue_12m_usd) over (), 0) as revenue_share_before

    from ranked

),

recent_demand as (

    -- 7-day buckets counted back from the as-of date: 0 = the last 7 days, ..., 25.
    select
        demand.sku,
        demand.ordered_qty,
        floor((data_bounds.as_of_date - demand.date_day) / 7) as weeks_ago

    from {{ ref('int_sku_demand__daily') }} as demand
    cross join data_bounds
    where demand.date_day > data_bounds.as_of_date - 182

),

weekly as (

    select
        sku,
        weeks_ago,
        sum(ordered_qty) as weekly_qty
    from recent_demand
    group by sku, weeks_ago

),

variability as (

    select
        sku,
        avg(weekly_qty) as weekly_demand_mean,
        stddev_samp(weekly_qty) as weekly_demand_std,
        stddev_samp(weekly_qty) / nullif(avg(weekly_qty), 0) as demand_cv

    from weekly
    group by sku

),

classified as (

    select
        shares.sku,
        shares.revenue_12m_usd,
        shares.revenue_share_before,
        case
            when shares.revenue_12m_usd <= 0 then 'C'
            when shares.revenue_share_before < {{ abc['a'] }} then 'A'
            when shares.revenue_share_before < {{ abc['b'] }} then 'B'
            else 'C'
        end as abc_class,
        variability.weekly_demand_mean,
        variability.weekly_demand_std,
        variability.demand_cv,
        case
            when variability.demand_cv is null then 'Z'
            when variability.demand_cv < {{ xyz['x'] }} then 'X'
            when variability.demand_cv <= {{ xyz['y'] }} then 'Y'
            else 'Z'
        end as xyz_class

    from shares
    left join variability
        on shares.sku = variability.sku

)

select * from classified
