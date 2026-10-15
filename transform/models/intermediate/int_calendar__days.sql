-- Grain: one row per day the data covers, from the first to the last inventory movement.
-- as_of_date (the last day of data) anchors every "trailing N days" metric, so results
-- don't depend on when dbt happens to run.

with

spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2023-01-01' as date)",
        end_date="cast('2028-01-01' as date)",
    ) }}

),

bounds as (

    select
        min(movement_date) as first_date,
        max(movement_date) as as_of_date
    from {{ ref('stg_erp__inventory_movements') }}

),

shows as (

    select * from {{ ref('gem_show_calendar') }}

),

days as (

    select
        cast(spine.date_day as date) as date_day,
        bounds.as_of_date,
        shows.show_name,
        shows.warehouse_id as show_warehouse_id,
        shows.show_name is not null as is_show_day

    from spine
    cross join bounds
    left join shows
        on cast(spine.date_day as date) between shows.start_date and shows.end_date
    where cast(spine.date_day as date) between bounds.first_date and bounds.as_of_date

)

select * from days
