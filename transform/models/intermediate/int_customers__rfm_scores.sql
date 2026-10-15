-- Grain: one row per canonical customer (duplicates merged).
-- Raw RFM metrics over the trailing 12 months and 1-5 quintile scores (5 = best):
--   recency    days since the last order (any time); fewer days scores higher
--   frequency  orders in the trailing 12 months
--   monetary   net revenue in the trailing 12 months
-- Segment labels are applied in mart_customer_rfm so the rules can be unit-tested.

with

data_bounds as (

    select max(date_day) as as_of_date from {{ ref('int_calendar__days') }}

),

customers as (

    select distinct canonical_customer_id
    from {{ ref('int_customers__deduplicated') }}

),

lines as (

    select * from {{ ref('int_order_lines__enriched') }}

),

orders as (

    select
        canonical_customer_id,
        order_id,
        order_date,
        sum(net_revenue_usd) as order_revenue_usd
    from lines
    group by canonical_customer_id, order_id, order_date

),

metrics as (

    select
        customers.canonical_customer_id,
        min(orders.order_date) as first_order_date,
        max(orders.order_date) as last_order_date,
        (max(data_bounds.as_of_date) - max(orders.order_date)) as recency_days,
        count(distinct case
            when orders.order_date > data_bounds.as_of_date - 365 then orders.order_id
        end) as frequency_12m,
        coalesce(sum(case
            when orders.order_date > data_bounds.as_of_date - 365 then orders.order_revenue_usd
        end), 0) as monetary_12m_usd

    from customers
    cross join data_bounds
    left join orders
        on customers.canonical_customer_id = orders.canonical_customer_id
    group by customers.canonical_customer_id

),

scored as (

    select
        *,
        ntile(5) over (order by coalesce(recency_days, 100000) desc) as recency_score,
        ntile(5) over (order by frequency_12m) as frequency_score,
        ntile(5) over (order by monetary_12m_usd) as monetary_score

    from metrics

)

select * from scored
