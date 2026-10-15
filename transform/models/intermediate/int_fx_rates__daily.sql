-- Grain: one row per currency per day.
-- units_per_usd comes from the committed monthly FX seed: the same rates the ERP (the
-- generator) used to price purchase orders, so USD costs reconcile exactly.
-- fred_units_per_usd is FRED's daily rate, forward-filled over weekends and holidays, for
-- context (null for MGA and MAD, which FRED doesn't publish, and for USD).

with

days as (

    select date_day from {{ ref('int_calendar__days') }}

),

monthly as (

    select * from {{ ref('fx_static_rates') }}

),

fred as (

    select
        observation_date,
        observation_value,
        case series_id
            when 'DEXINUS' then 'INR'
            when 'DEXBZUS' then 'BRL'
            when 'DEXCHUS' then 'CNY'
            when 'DEXMXUS' then 'MXN'
        end as currency
    from {{ ref('stg_fred__observations') }}
    where series_id in ('DEXINUS', 'DEXBZUS', 'DEXCHUS', 'DEXMXUS')

),

fred_ranges as (

    select
        currency,
        observation_value,
        observation_date as valid_from,
        coalesce(
            lead(observation_date) over (partition by currency order by observation_date),
            cast('9999-12-31' as date)
        ) as valid_to
    from fred

),

daily as (

    select
        days.date_day,
        monthly.currency,
        monthly.units_per_usd,
        monthly.source as rate_source,
        fred_ranges.observation_value as fred_units_per_usd

    from days
    inner join monthly
        on {{ dbt.date_trunc('month', 'days.date_day') }} = monthly.month
    left join fred_ranges
        on
            monthly.currency = fred_ranges.currency
            and days.date_day >= fred_ranges.valid_from
            and days.date_day < fred_ranges.valid_to

)

select * from daily
