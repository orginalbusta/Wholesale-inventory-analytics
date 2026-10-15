-- Grain: one row per SKU (current attributes), with its ABC/XYZ class.

with

products as (

    select * from {{ ref('stg_erp__products') }}

),

suppliers as (

    select * from {{ ref('stg_erp__suppliers') }}

),

classes as (

    select * from {{ ref('int_sku__abc_xyz') }}

)

select
    cast(products.sku as varchar) as sku,
    cast(products.product_name as varchar) as product_name,
    cast(products.category as varchar) as category,
    cast(products.material as varchar) as material,
    cast(products.unit_of_measure as varchar) as unit_of_measure,
    cast(products.primary_supplier_id as varchar) as supplier_id,
    cast(suppliers.supplier_name as varchar) as supplier_name,
    cast(suppliers.country as varchar) as supplier_country,
    cast(products.unit_cost_usd as double) as unit_cost_usd,
    cast(products.list_price_usd as double) as list_price_usd,
    cast(products.case_pack_qty as integer) as case_pack_qty,
    cast(products.launch_date as date) as launch_date,
    cast(products.discontinued_date as date) as discontinued_date,
    cast(products.is_active as boolean) as is_active,
    cast(classes.abc_class as varchar) as abc_class,
    cast(classes.xyz_class as varchar) as xyz_class,
    cast(classes.revenue_12m_usd as double) as revenue_12m_usd,
    cast(classes.demand_cv as double) as weekly_demand_cv

from products
left join suppliers
    on products.primary_supplier_id = suppliers.supplier_id
left join classes
    on products.sku = classes.sku
