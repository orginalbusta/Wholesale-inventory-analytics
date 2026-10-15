-- Grain: one row per SKU. Everything the reorder calculation needs, in one place:
--   demand_mean_daily / demand_std_daily  trailing 90 days of TRUE demand (incl. unfilled),
--                                         over the days the SKU was on sale.
--   demand_source                         'historical_90d'. The future forecasting layer
--                                         replaces the two demand columns and sets this to
--                                         'forecast_<model>' (docs/06_future_ds_layer.md).
--   lead_time_mean_days / _std_days       actual lead times of the primary supplier's
--                                         received POs in the trailing 12 months (falls
--                                         back to all history, then to the quoted lead time).
--   on_hand_qty / on_order_qty            stock in all warehouses and open PO quantity.
--   z_score                               from the ABC x XYZ service-level policy seed.

with

data_bounds as (

    select max(date_day) as as_of_date from {{ ref('int_calendar__days') }}

),

products as (

    select * from {{ ref('stg_erp__products') }}

),

classes as (

    select * from {{ ref('int_sku__abc_xyz') }}

),

policy as (

    select * from {{ ref('abc_xyz_policy') }}

),

demand as (

    select
        demand.sku,
        avg(demand.ordered_qty) as demand_mean_daily,
        coalesce(stddev_samp(demand.ordered_qty), 0) as demand_std_daily,
        count(*) as demand_days_observed

    from {{ ref('int_sku_demand__daily') }} as demand
    cross join data_bounds
    where
        demand.date_day
        > data_bounds.as_of_date - {{ var('demand_window_days') }}
    group by demand.sku

),

received_pos as (

    select
        po.supplier_id,
        po.po_id,
        po.order_date,
        max(po.actual_lead_time_days) as lead_time_days,
        max(po.quoted_lead_time_days) as quoted_lead_time_days

    from {{ ref('int_purchase_order_lines__enriched') }} as po
    where po.is_received
    group by po.supplier_id, po.po_id, po.order_date

),

lead_times as (

    select
        received_pos.supplier_id,
        avg(case
            when
                received_pos.order_date
                > data_bounds.as_of_date - {{ var('lead_time_window_days') }}
                then received_pos.lead_time_days
        end) as lead_time_mean_recent,
        stddev_samp(case
            when
                received_pos.order_date
                > data_bounds.as_of_date - {{ var('lead_time_window_days') }}
                then received_pos.lead_time_days
        end) as lead_time_std_recent,
        avg(received_pos.lead_time_days) as lead_time_mean_all,
        stddev_samp(received_pos.lead_time_days) as lead_time_std_all,
        avg(received_pos.quoted_lead_time_days) as quoted_lead_time_mean

    from received_pos
    cross join data_bounds
    group by received_pos.supplier_id

),

quoted as (

    select
        supplier_id,
        avg(quoted_lead_time_days) as quoted_lead_time_days
    from {{ ref('int_purchase_order_lines__enriched') }}
    group by supplier_id

),

stock as (

    select
        balance.sku,
        sum(balance.on_hand_qty) as on_hand_qty
    from {{ ref('int_inventory__daily_balance') }} as balance
    inner join data_bounds
        on balance.date_day = data_bounds.as_of_date
    group by balance.sku

),

on_order as (

    select
        sku,
        sum(open_quantity) as on_order_qty
    from {{ ref('int_purchase_order_lines__enriched') }}
    group by sku

),

final as (

    select
        products.sku,
        products.category,
        products.primary_supplier_id as supplier_id,
        products.case_pack_qty,
        products.is_active,
        products.launch_date <= data_bounds.as_of_date as is_launched,
        classes.abc_class,
        classes.xyz_class,
        policy.target_service_level,
        policy.z_score,
        coalesce(demand.demand_mean_daily, 0) as demand_mean_daily,
        coalesce(demand.demand_std_daily, 0) as demand_std_daily,
        'historical_{{ var("demand_window_days") }}d' as demand_source,
        coalesce(
            lead_times.lead_time_mean_recent,
            lead_times.lead_time_mean_all,
            quoted.quoted_lead_time_days
        ) as lead_time_mean_days,
        coalesce(
            lead_times.lead_time_std_recent,
            lead_times.lead_time_std_all,
            0
        ) as lead_time_std_days,
        case
            when lead_times.lead_time_mean_recent is not null then 'actual_trailing_12m'
            when lead_times.lead_time_mean_all is not null then 'actual_all_history'
            else 'quoted'
        end as lead_time_source,
        coalesce(stock.on_hand_qty, 0) as on_hand_qty,
        coalesce(on_order.on_order_qty, 0) as on_order_qty,
        data_bounds.as_of_date

    from products
    cross join data_bounds
    left join classes
        on products.sku = classes.sku
    left join policy
        on classes.abc_class = policy.abc_class and classes.xyz_class = policy.xyz_class
    left join demand
        on products.sku = demand.sku
    left join lead_times
        on products.primary_supplier_id = lead_times.supplier_id
    left join quoted
        on products.primary_supplier_id = quoted.supplier_id
    left join stock
        on products.sku = stock.sku
    left join on_order
        on products.sku = on_order.sku

)

select * from final
