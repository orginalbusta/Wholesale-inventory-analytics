-- Grain: one row per purchase order (latest version).
-- Handles planted issue 8: expected_arrival_date arrives as a string in two formats
-- (YYYY-MM-DD and MM/DD/YYYY) and is parsed with parse_mixed_date().

with

source as (

    select * from {{ source('erp', 'purchase_orders') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by po_id
        order by updated_at desc, _extracted_at desc
    ) = 1

),

renamed as (

    select
        po_id,
        supplier_id,
        cast(order_date as date) as order_date,
        {{ parse_mixed_date('expected_arrival_date') }} as expected_arrival_date,
        expected_arrival_date as expected_arrival_date_raw,
        cast(actual_arrival_date as date) as actual_arrival_date,
        lower(trim(status)) as po_status,
        upper(trim(currency)) as currency,
        cast(updated_at as timestamp) as updated_at,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

)

select * from renamed
