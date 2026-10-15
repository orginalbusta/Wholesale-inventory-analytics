-- Grain: one row per canonical customer. RFM scores (1-5, 5 = best) and a segment label.
-- Rules are checked in order; the first match wins:
--   New           first order within the last 90 days
--   Champions     recency >= 4 and frequency >= 4
--   Loyal         recency >= 3 and frequency >= 3
--   At Risk       recency <= 2 and frequency >= 3   (used to buy often, has gone quiet)
--   Hibernating   recency <= 2 and frequency <= 2
--   Needs Attention  everyone else

with

scores as (

    select * from {{ ref('int_customers__rfm_scores') }}

),

data_bounds as (

    select max(date_day) as as_of_date from {{ ref('int_calendar__days') }}

),

customers as (

    select * from {{ ref('dim_customers') }}

),

segmented as (

    select
        scores.*,
        case
            when
                scores.first_order_date > data_bounds.as_of_date - 90
                then 'New'
            when scores.recency_score >= 4 and scores.frequency_score >= 4 then 'Champions'
            when scores.recency_score >= 3 and scores.frequency_score >= 3 then 'Loyal'
            when scores.recency_score <= 2 and scores.frequency_score >= 3 then 'At Risk'
            when scores.recency_score <= 2 and scores.frequency_score <= 2 then 'Hibernating'
            else 'Needs Attention'
        end as segment

    from scores
    cross join data_bounds

)

select
    cast(segmented.canonical_customer_id as varchar) as customer_id,
    cast(customers.customer_name as varchar) as customer_name,
    cast(customers.customer_type as varchar) as customer_type,
    cast(customers.state as varchar) as state,
    cast(segmented.first_order_date as date) as first_order_date,
    cast(segmented.last_order_date as date) as last_order_date,
    cast(segmented.recency_days as integer) as recency_days,
    cast(segmented.frequency_12m as bigint) as frequency_12m,
    cast(segmented.monetary_12m_usd as double) as monetary_12m_usd,
    cast(segmented.recency_score as integer) as recency_score,
    cast(segmented.frequency_score as integer) as frequency_score,
    cast(segmented.monetary_score as integer) as monetary_score,
    cast(segmented.segment as varchar) as segment

from segmented
left join customers
    on segmented.canonical_customer_id = customers.customer_id
