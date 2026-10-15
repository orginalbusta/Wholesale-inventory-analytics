-- Grain: one row per SKU per price version, with the date range it was in effect.
-- valid_to is exclusive; the current version has valid_to = 9999-12-31.
-- Built from the ERP price-change log so cost "as of" any date is available for the whole
-- history, not only from the first snapshot run (see docs/DECISIONS.md).

with

changes as (

    select * from {{ ref('stg_erp__product_price_history') }}

),

-- Several changes on the same day: the last one wins for that day.
daily as (

    select *
    from changes
    qualify row_number() over (
        partition by sku, effective_date
        order by changed_at desc, price_change_id desc
    ) = 1

),

versions as (

    select
        sku,
        effective_date as valid_from,
        coalesce(
            lead(effective_date) over (partition by sku order by effective_date),
            cast('9999-12-31' as date)
        ) as valid_to,
        unit_cost_usd,
        list_price_usd

    from daily

)

select * from versions
