-- Grain: one row per SKU (all warehouses), as of the last day of data.
-- Answers: what is on hand, what is it worth, how many days of supply, and which SKUs
-- are dead stock (on hand > 0 and no sale in the last `dead_stock_days` days).

with

inputs as (

    select * from {{ ref('int_sku__reorder_inputs') }}

),

products as (

    select * from {{ ref('stg_erp__products') }}

),

last_sale as (

    select
        sku,
        max(date_day) as last_sale_date
    from {{ ref('int_sku_demand__daily') }}
    where fulfilled_qty > 0
    group by sku

),

health as (

    select
        inputs.sku,
        products.product_name,
        inputs.category,
        inputs.supplier_id,
        inputs.is_active,
        inputs.abc_class,
        inputs.xyz_class,
        inputs.on_hand_qty,
        inputs.on_hand_qty * products.unit_cost_usd as on_hand_value_usd,
        inputs.on_order_qty,
        inputs.demand_mean_daily as avg_daily_demand_90d,
        case
            when inputs.demand_mean_daily > 0 then inputs.on_hand_qty / inputs.demand_mean_daily
        end as days_of_supply,
        last_sale.last_sale_date,
        (inputs.as_of_date - last_sale.last_sale_date) as days_since_last_sale,
        inputs.on_hand_qty > 0
        and (
            last_sale.last_sale_date is null
            or (inputs.as_of_date - last_sale.last_sale_date) >= {{ var('dead_stock_days') }}
        ) as is_dead_stock,
        inputs.as_of_date

    from inputs
    inner join products
        on inputs.sku = products.sku
    left join last_sale
        on inputs.sku = last_sale.sku
    where inputs.is_launched

)

select
    cast(sku as varchar) as sku,
    cast(product_name as varchar) as product_name,
    cast(category as varchar) as category,
    cast(supplier_id as varchar) as supplier_id,
    cast(is_active as boolean) as is_active,
    cast(abc_class as varchar) as abc_class,
    cast(xyz_class as varchar) as xyz_class,
    cast(on_hand_qty as double) as on_hand_qty,
    cast(on_hand_value_usd as double) as on_hand_value_usd,
    cast(on_order_qty as double) as on_order_qty,
    cast(avg_daily_demand_90d as double) as avg_daily_demand_90d,
    cast(days_of_supply as double) as days_of_supply,
    cast(last_sale_date as date) as last_sale_date,
    cast(days_since_last_sale as integer) as days_since_last_sale,
    cast(is_dead_stock as boolean) as is_dead_stock,
    cast(as_of_date as date) as as_of_date

from health
