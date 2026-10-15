-- Grain: one row per sales order line.
-- Handles planted issue 3: SKU variants are normalized to the canonical format.
-- Handles planted issue 6: negative-quantity lines are returns; they are flagged with
-- is_return_line and their quantities made positive, so quantities are always >= 0.
-- Orphan SKUs (issue 9) pass through and are caught by a warn-level relationships test.

with

source as (

    select * from {{ source('erp', 'sales_order_lines') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by order_line_id
        order by _extracted_at desc
    ) = 1

),

renamed as (

    select
        order_line_id,
        order_id,
        cast(line_no as integer) as line_no,
        {{ normalize_sku('sku') }} as sku,
        sku as sku_raw,
        quantity < 0 as is_return_line,
        abs(quantity) as quantity,
        abs(quantity_fulfilled) as quantity_fulfilled,
        cast(unit_price_usd as {{ dbt.type_numeric() }}) as unit_price_usd,
        coalesce(line_discount_pct, 0) / 100.0 as line_discount_rate,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

)

select * from renamed
