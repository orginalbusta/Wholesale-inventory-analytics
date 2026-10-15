-- Grain: one row per supplier, with lead-time statistics from received purchase orders.

with

suppliers as (

    select * from {{ ref('stg_erp__suppliers') }}

),

received_pos as (

    select
        supplier_id,
        po_id,
        max(quoted_lead_time_days) as quoted_lead_time_days,
        max(actual_lead_time_days) as actual_lead_time_days,
        min(case when is_on_time then 1 else 0 end) = 1 as is_on_time
    from {{ ref('int_purchase_order_lines__enriched') }}
    where is_received
    group by supplier_id, po_id

),

stats as (

    select
        supplier_id,
        count(*) as received_po_count,
        avg(quoted_lead_time_days) as quoted_lead_time_mean_days,
        avg(actual_lead_time_days) as lead_time_mean_days,
        stddev_samp(actual_lead_time_days) as lead_time_std_days,
        avg(case when is_on_time then 1.0 else 0.0 end) as on_time_rate
    from received_pos
    group by supplier_id

)

select
    cast(suppliers.supplier_id as varchar) as supplier_id,
    cast(suppliers.supplier_name as varchar) as supplier_name,
    cast(suppliers.country as varchar) as country,
    cast(suppliers.currency as varchar) as currency,
    cast(suppliers.payment_terms as varchar) as payment_terms,
    cast(suppliers.min_order_value_usd as double) as min_order_value_usd,
    cast(coalesce(stats.received_po_count, 0) as bigint) as received_po_count,
    cast(stats.quoted_lead_time_mean_days as double) as quoted_lead_time_mean_days,
    cast(stats.lead_time_mean_days as double) as lead_time_mean_days,
    cast(stats.lead_time_std_days as double) as lead_time_std_days,
    cast(stats.on_time_rate as double) as on_time_rate

from suppliers
left join stats
    on suppliers.supplier_id = stats.supplier_id
