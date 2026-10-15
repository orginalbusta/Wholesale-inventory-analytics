-- Grain: one row per day the data covers. Calendar fields, a simple fiscal calendar
-- (fiscal year = calendar year, a planning assumption) and gem-show flags, which the
-- forecasting layer can use as features.

with

days as (

    select * from {{ ref('int_calendar__days') }}

)

select
    cast(date_day as date) as date_day,
    cast({{ dbt.date_trunc('week', 'date_day') }} as date) as week_start_date,
    cast({{ dbt.date_trunc('month', 'date_day') }} as date) as month_start_date,
    cast({{ dbt.date_trunc('quarter', 'date_day') }} as date) as quarter_start_date,
    cast(extract(year from date_day) as integer) as calendar_year,
    cast(extract(quarter from date_day) as integer) as calendar_quarter,
    cast(extract(month from date_day) as integer) as calendar_month,
    cast(extract(day from date_day) as integer) as day_of_month,
    cast({{ dbt_date.day_of_week('date_day', isoweek=true) }} as integer) as iso_day_of_week,
    cast({{ dbt_date.day_of_week('date_day', isoweek=true) }} in (6, 7) as boolean) as is_weekend,
    cast(extract(year from date_day) as integer) as fiscal_year,
    cast(extract(quarter from date_day) as integer) as fiscal_quarter,
    cast(is_show_day as boolean) as is_show_day,
    cast(show_name as varchar) as show_name,
    cast(show_warehouse_id as varchar) as show_warehouse_id,
    cast(date_day = as_of_date as boolean) as is_as_of_date

from days
