-- After SKU normalization, every distinct SKU on order lines is either a known product or
-- quarantined as an orphan. Nothing falls through the cracks.
-- Dagster shows this test as a check on stg_erp__sales_order_lines.
{{ config(meta={'dagster': {'ref': {'name': 'stg_erp__sales_order_lines'}}}) }}

with

line_skus as (

    select distinct sku from {{ ref('stg_erp__sales_order_lines') }}

),

known as (

    select line_skus.sku
    from line_skus
    inner join {{ ref('dim_products') }} as products
        on line_skus.sku = products.sku

),

orphans as (

    select distinct sku_normalized as sku from {{ ref('int_order_lines__orphans') }}

)

select
    (select count(*) from line_skus) as line_skus,
    (select count(*) from known) as known_skus,
    (select count(*) from orphans) as orphan_skus
where
    (select count(*) from line_skus)
    <> (select count(*) from known) + (select count(*) from orphans)
