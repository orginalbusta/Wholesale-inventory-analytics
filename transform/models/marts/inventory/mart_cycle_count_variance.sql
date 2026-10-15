-- Grain: one row per SKU x warehouse x month with at least one cycle count.
-- Shrinkage = stock the ledger said was there but the count didn't find, valued at the
-- unit cost on the count date. Big misses (planted issue 10) are counted separately.

with

counts as (

    select * from {{ ref('stg_erp__cycle_counts') }}

),

costs as (

    select * from {{ ref('int_product_costs__history') }}

),

valued as (

    select
        counts.*,
        costs.unit_cost_usd
    from counts
    left join costs
        on
            counts.sku = costs.sku
            and counts.count_date >= costs.valid_from
            and counts.count_date < costs.valid_to

),

monthly as (

    select
        sku,
        warehouse_id,
        cast({{ dbt.date_trunc('month', 'count_date') }} as date) as month_start_date,
        count(*) as n_counts,
        sum(case when variance_qty <> 0 then 1 else 0 end) as n_counts_with_variance,
        sum(case when variance_pct < -0.15 then 1 else 0 end) as n_big_misses,
        sum(system_qty) as system_qty,
        sum(variance_qty) as net_variance_qty,
        sum(case when variance_qty < 0 then -variance_qty else 0 end) as shrinkage_qty,
        sum(case when variance_qty < 0 then -variance_qty * unit_cost_usd else 0 end)
            as shrinkage_value_usd,
        sum(variance_qty * unit_cost_usd) as net_variance_value_usd

    from valued
    group by 1, 2, 3

)

select
    cast(sku as varchar) as sku,
    cast(warehouse_id as varchar) as warehouse_id,
    cast(month_start_date as date) as month_start_date,
    cast(n_counts as integer) as n_counts,
    cast(n_counts_with_variance as integer) as n_counts_with_variance,
    cast(n_big_misses as integer) as n_big_misses,
    cast(system_qty as double) as system_qty,
    cast(net_variance_qty as double) as net_variance_qty,
    cast(shrinkage_qty as double) as shrinkage_qty,
    cast(shrinkage_value_usd as double) as shrinkage_value_usd,
    cast(net_variance_value_usd as double) as net_variance_value_usd,
    cast(net_variance_qty / nullif(system_qty, 0) as double) as variance_pct

from monthly
