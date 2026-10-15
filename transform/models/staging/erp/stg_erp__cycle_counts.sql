-- Grain: one row per cycle count (SKU x warehouse x count date).
-- Big misses (planted issue 10) show up as large negative variance_pct; a warn-level test
-- flags them for the shrinkage analysis.

with

source as (

    select * from {{ source('erp', 'cycle_counts') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by count_id
        order by _extracted_at desc
    ) = 1

),

renamed as (

    select
        count_id,
        cast(count_date as date) as count_date,
        warehouse_id,
        {{ normalize_sku('sku') }} as sku,
        system_qty,
        counted_qty,
        counted_qty - system_qty as variance_qty,
        (counted_qty - system_qty) / nullif(system_qty, 0) as variance_pct,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

)

select * from renamed
