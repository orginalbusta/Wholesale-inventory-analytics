-- Grain: one row per canonical customer (duplicate ERP records merged, planted issue 1).
-- Attributes come from the canonical (earliest) record; order history spans all records.

with

dedup as (

    select * from {{ ref('int_customers__deduplicated') }}

),

customers as (

    select * from {{ ref('stg_erp__customers') }}

),

record_counts as (

    select
        canonical_customer_id,
        count(*) as n_erp_records
    from dedup
    group by canonical_customer_id

),

history as (

    select
        canonical_customer_id,
        min(order_date) as first_order_date,
        max(order_date) as last_order_date,
        count(distinct order_id) as lifetime_orders,
        sum(net_revenue_usd) as lifetime_net_revenue_usd,
        sum(gross_margin_usd) as lifetime_gross_margin_usd
    from {{ ref('int_order_lines__enriched') }}
    group by canonical_customer_id

)

select
    cast(customers.customer_id as varchar) as customer_id,
    cast(customers.customer_name as varchar) as customer_name,
    cast(customers.customer_type as varchar) as customer_type,
    cast(customers.state as varchar) as state,
    cast(customers.credit_terms as varchar) as credit_terms,
    cast(customers.sales_rep_id as varchar) as sales_rep_id,
    cast(customers.is_email_valid as boolean) as has_valid_email,
    cast(record_counts.n_erp_records as integer) as n_erp_records,
    cast(history.first_order_date as date) as first_order_date,
    cast(history.last_order_date as date) as last_order_date,
    cast(coalesce(history.lifetime_orders, 0) as bigint) as lifetime_orders,
    cast(coalesce(history.lifetime_net_revenue_usd, 0) as double) as lifetime_net_revenue_usd,
    cast(coalesce(history.lifetime_gross_margin_usd, 0) as double) as lifetime_gross_margin_usd

from record_counts
inner join customers
    on record_counts.canonical_customer_id = customers.customer_id
left join history
    on record_counts.canonical_customer_id = history.canonical_customer_id
