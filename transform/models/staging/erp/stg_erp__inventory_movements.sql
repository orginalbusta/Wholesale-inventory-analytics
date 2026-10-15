-- Grain: one row per stock movement (signed: + into stock, - out of stock).

with

source as (

    select * from {{ source('erp', 'inventory_movements') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by movement_id
        order by _extracted_at desc
    ) = 1

),

renamed as (

    select
        movement_id,
        cast(movement_ts as timestamp) as movement_ts,
        cast(movement_ts as date) as movement_date,
        warehouse_id,
        {{ normalize_sku('sku') }} as sku,
        lower(trim(movement_type)) as movement_type,
        quantity,
        reference_id,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

)

select * from renamed
