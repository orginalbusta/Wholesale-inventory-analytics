-- Grain: one row per active, launched SKU. What to reorder now, and how much.
--
--   safety_stock       = z * sqrt( L * sigma_d^2 + d^2 * sigma_L^2 )
--   reorder_point      = d * L + safety_stock
--   inventory_position = on_hand + on_order
--   reorder_now        = inventory_position <= reorder_point
--   suggested_qty      = reorder_point + d * review_period - inventory_position,
--                        rounded up to whole case packs (0 when reorder_now is false)
--
-- d / sigma_d: demand_mean_daily / demand_std_daily (historical 90 days today; the
-- forecasting layer swaps them in int_sku__reorder_inputs and sets demand_source).
-- L / sigma_L: the primary supplier's actual lead times, not the quoted ones.
-- z: from the ABC x XYZ service-level policy seed.
-- The dashboard's what-if page recomputes these formulas in the browser from this mart's input
-- columns; tests/test_dashboard_whatif.py checks that both agree at the default inputs.

with

inputs as (

    select * from {{ ref('int_sku__reorder_inputs') }}
    where is_active and is_launched

),

policy as (

    select
        *,
        {{ safety_stock(
            z='z_score',
            demand_mean='demand_mean_daily',
            demand_std='demand_std_daily',
            lead_time_mean='lead_time_mean_days',
            lead_time_std='lead_time_std_days',
        ) }} as safety_stock_qty,
        on_hand_qty + on_order_qty as inventory_position

    from inputs

),

reorder as (

    select
        *,
        demand_mean_daily * lead_time_mean_days + safety_stock_qty as reorder_point_qty

    from policy

),

recommended as (

    select
        *,
        inventory_position <= reorder_point_qty and demand_mean_daily > 0 as reorder_now,
        reorder_point_qty + demand_mean_daily * {{ var('review_period_days') }} - inventory_position
            as raw_order_qty

    from reorder

)

select
    cast(sku as varchar) as sku,
    cast(category as varchar) as category,
    cast(supplier_id as varchar) as supplier_id,
    cast(abc_class as varchar) as abc_class,
    cast(xyz_class as varchar) as xyz_class,
    cast(target_service_level as double) as target_service_level,
    cast(z_score as double) as z_score,
    cast(demand_mean_daily as double) as demand_mean_daily,
    cast(demand_std_daily as double) as demand_std_daily,
    cast(demand_source as varchar) as demand_source,
    cast(lead_time_mean_days as double) as lead_time_mean_days,
    cast(lead_time_std_days as double) as lead_time_std_days,
    cast(lead_time_source as varchar) as lead_time_source,
    cast(safety_stock_qty as double) as safety_stock_qty,
    cast(reorder_point_qty as double) as reorder_point_qty,
    cast(on_hand_qty as double) as on_hand_qty,
    cast(on_order_qty as double) as on_order_qty,
    cast(inventory_position as double) as inventory_position,
    cast(reorder_now as boolean) as reorder_now,
    cast(case_pack_qty as integer) as case_pack_qty,
    cast(unit_cost_usd as double) as unit_cost_usd,
    cast({{ var('review_period_days') }} as integer) as review_period_days,
    cast(
        case
            when
                reorder_now
                then {{ round_up_to_case_pack('greatest(raw_order_qty, 0)', 'case_pack_qty') }}
            else 0
        end as double
    ) as suggested_order_qty,
    cast(as_of_date as date) as as_of_date

from recommended
