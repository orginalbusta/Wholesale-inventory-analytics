-- Grain: one row per SKU x warehouse x day: end-of-day stock on hand and its value at the
-- unit cost in effect that day. Incremental by day: each run (re)builds the days inside the
-- lookback window; earlier days never change because the ledger is append-only.

{{
    config(
        materialized='incremental',
        unique_key=['sku', 'warehouse_id', 'date_day'],
        incremental_strategy='delete+insert',
        on_schema_change='fail',
    )
}}

with

balances as (

    select * from {{ ref('int_inventory__daily_balance') }}

    {% if is_incremental() %}
        where date_day > (
            select {{ dbt.dateadd('day', -var('incremental_lookback_days'), 'max(date_day)') }}
            from {{ this }}
        )
    {% endif %}

),

costs as (

    select * from {{ ref('int_product_costs__history') }}

)

select
    cast(balances.sku as varchar) as sku,
    cast(balances.warehouse_id as varchar) as warehouse_id,
    cast(balances.date_day as date) as date_day,
    cast(balances.on_hand_qty as double) as on_hand_qty,
    cast(balances.net_change_qty as double) as net_change_qty,
    cast(balances.sold_qty as double) as sold_qty,
    cast(balances.received_qty as double) as received_qty,
    cast(costs.unit_cost_usd as double) as unit_cost_usd,
    cast(balances.on_hand_qty * costs.unit_cost_usd as double) as on_hand_value_usd

from balances
left join costs
    on
        balances.sku = costs.sku
        and balances.date_day >= costs.valid_from
        and balances.date_day < costs.valid_to
