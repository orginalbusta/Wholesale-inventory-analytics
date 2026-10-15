-- Grain: one row per SKU per month the SKU was on sale.
--   stockout_days        days with demand that could not be filled (in any warehouse)
--   zero_stock_days_main days the main warehouse ended with nothing on hand
--   unfilled_qty / unfilled_revenue_estimate_usd  the demand lost, valued at the prices
--                        customers were quoted (including stockout-cancelled orders)

with

demand as (

    select * from {{ ref('int_sku_demand__daily') }}

),

main_stock as (

    select
        sku,
        date_day,
        on_hand_qty
    from {{ ref('int_inventory__daily_balance') }}
    where warehouse_id = 'SD-MAIN'

),

classes as (

    select * from {{ ref('int_sku__abc_xyz') }}

),

products as (

    select * from {{ ref('stg_erp__products') }}

),

monthly as (

    select
        demand.sku,
        cast({{ dbt.date_trunc('month', 'demand.date_day') }} as date) as month_start_date,
        count(*) as days_on_sale,
        sum(case when demand.ordered_qty > 0 then 1 else 0 end) as demand_days,
        sum(case when demand.unfilled_qty > 0 then 1 else 0 end) as stockout_days,
        sum(case when coalesce(main_stock.on_hand_qty, 0) <= 0 then 1 else 0 end)
            as zero_stock_days_main,
        sum(demand.ordered_qty) as ordered_qty,
        sum(demand.fulfilled_qty) as fulfilled_qty,
        sum(demand.unfilled_qty) as unfilled_qty,
        sum(demand.unfilled_revenue_usd) as unfilled_revenue_estimate_usd

    from demand
    left join main_stock
        on demand.sku = main_stock.sku and demand.date_day = main_stock.date_day
    group by 1, 2

)

select
    cast(monthly.sku as varchar) as sku,
    cast(monthly.month_start_date as date) as month_start_date,
    cast(products.category as varchar) as category,
    cast(classes.abc_class as varchar) as abc_class,
    cast(monthly.days_on_sale as integer) as days_on_sale,
    cast(monthly.demand_days as integer) as demand_days,
    cast(monthly.stockout_days as integer) as stockout_days,
    cast(monthly.zero_stock_days_main as integer) as zero_stock_days_main,
    cast(monthly.ordered_qty as double) as ordered_qty,
    cast(monthly.fulfilled_qty as double) as fulfilled_qty,
    cast(monthly.unfilled_qty as double) as unfilled_qty,
    cast(
        case
            when monthly.ordered_qty > 0 then monthly.fulfilled_qty / monthly.ordered_qty
        end as double
    )
        as fill_rate,
    cast(monthly.unfilled_revenue_estimate_usd as double) as unfilled_revenue_estimate_usd

from monthly
inner join products
    on monthly.sku = products.sku
left join classes
    on monthly.sku = classes.sku
