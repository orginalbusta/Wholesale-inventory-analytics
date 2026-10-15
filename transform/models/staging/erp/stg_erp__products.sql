-- Grain: one row per SKU (latest version).
-- Handles planted issue 2: inconsistent category labels are trimmed, lowercased,
-- whitespace-collapsed and mapped to a canonical category via the category_mapping seed.

with

source as (

    select * from {{ source('erp', 'products') }}

),

category_mapping as (

    select * from {{ ref('category_mapping') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by sku
        order by updated_at desc, _extracted_at desc
    ) = 1

),

renamed as (

    select
        {{ normalize_sku('sku') }} as sku,
        trim(product_name) as product_name,
        category as category_raw,
        {{ normalize_label('category') }} as category_normalized,
        lower(trim(material)) as material,
        primary_supplier_id,
        lower(trim(unit_of_measure)) as unit_of_measure,
        cast(unit_cost_usd as {{ dbt.type_numeric() }}) as unit_cost_usd,
        cast(list_price_usd as {{ dbt.type_numeric() }}) as list_price_usd,
        cast(case_pack_qty as integer) as case_pack_qty,
        cast(launch_date as date) as launch_date,
        cast(discontinued_date as date) as discontinued_date,
        is_active,
        cast(updated_at as timestamp) as updated_at,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

),

mapped as (

    select
        renamed.sku,
        renamed.product_name,
        category_mapping.category,
        renamed.category_raw,
        renamed.material,
        renamed.primary_supplier_id,
        renamed.unit_of_measure,
        renamed.unit_cost_usd,
        renamed.list_price_usd,
        renamed.case_pack_qty,
        renamed.launch_date,
        renamed.discontinued_date,
        renamed.is_active,
        renamed.updated_at,
        renamed.extracted_at

    from renamed
    left join category_mapping
        on renamed.category_normalized = category_mapping.raw_category_normalized

)

select * from mapped
