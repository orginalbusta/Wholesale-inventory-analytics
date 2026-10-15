-- Grain: one row per supplier (latest extracted version).

with

source as (

    select * from {{ source('erp', 'suppliers') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by supplier_id
        order by _extracted_at desc
    ) = 1

),

renamed as (

    select
        supplier_id,
        trim(supplier_name) as supplier_name,
        trim(country) as country,
        upper(trim(currency)) as currency,
        upper(trim(payment_terms)) as payment_terms,
        cast(min_order_value_usd as {{ dbt.type_numeric() }}) as min_order_value_usd,
        cast(created_at as date) as created_date,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

)

select * from renamed
