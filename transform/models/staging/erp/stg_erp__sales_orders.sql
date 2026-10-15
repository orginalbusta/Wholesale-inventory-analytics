-- Grain: one row per sales order (latest version).
-- Handles planted issue 4 (re-extracted duplicate rows, some of them stale older versions)
-- and issue 5 (late-arriving status updates): raw keeps every extracted version, and this
-- model keeps the one with the latest updated_at.

with

source as (

    select * from {{ source('erp', 'sales_orders') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by order_id
        order by updated_at desc, _extracted_at desc
    ) = 1

),

renamed as (

    select
        order_id,
        customer_id,
        cast(order_date as date) as order_date,
        lower(trim(channel)) as channel,
        warehouse_id,
        lower(trim(status)) as order_status,
        lower(trim(cancel_reason)) as cancel_reason,
        cast(ship_date as date) as ship_date,
        coalesce(order_discount_pct, 0) / 100.0 as order_discount_rate,
        sales_rep_id,
        cast(updated_at as timestamp) as updated_at,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

)

select * from renamed
