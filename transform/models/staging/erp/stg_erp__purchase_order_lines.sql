-- Grain: one row per purchase order line (latest version: quantity_received is filled in
-- by a later extract when the PO arrives).

with

source as (

    select * from {{ source('erp', 'purchase_order_lines') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by po_line_id
        order by _extracted_at desc
    ) = 1

),

renamed as (

    select
        po_line_id,
        po_id,
        {{ normalize_sku('sku') }} as sku,
        quantity_ordered,
        quantity_received,
        cast(unit_cost_local as {{ dbt.type_numeric() }}) as unit_cost_local,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

)

select * from renamed
