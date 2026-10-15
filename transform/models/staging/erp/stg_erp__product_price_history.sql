-- Grain: one row per price change (the ERP's price-change log, plus each SKU's initial
-- price at setup). Used downstream for cost as of order date.

with

source as (

    select * from {{ source('erp', 'product_price_history') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by price_change_id
        order by _extracted_at desc
    ) = 1

),

renamed as (

    select
        price_change_id,
        {{ normalize_sku('sku') }} as sku,
        cast(effective_date as date) as effective_date,
        cast(unit_cost_usd as {{ dbt.type_numeric() }}) as unit_cost_usd,
        cast(list_price_usd as {{ dbt.type_numeric() }}) as list_price_usd,
        cast(changed_at as timestamp) as changed_at,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

)

select * from renamed
