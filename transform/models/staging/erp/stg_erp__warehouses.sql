-- Grain: one row per warehouse (latest extracted version).

with

source as (

    select * from {{ source('erp', 'warehouses') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by warehouse_id
        order by _extracted_at desc
    ) = 1

),

renamed as (

    select
        warehouse_id,
        trim(warehouse_name) as warehouse_name,
        lower(trim(warehouse_type)) as warehouse_type,
        trim(city) as city,
        upper(trim(state)) as state,
        is_seasonal,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

)

select * from renamed
