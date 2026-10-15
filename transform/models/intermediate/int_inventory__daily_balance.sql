-- Grain: one row per SKU x warehouse x day, from the pair's first movement to the as-of date.
-- on_hand_qty is the running sum of the signed ledger: the end-of-day stock on hand.

with

movements as (

    select * from {{ ref('stg_erp__inventory_movements') }}

),

days as (

    select date_day from {{ ref('int_calendar__days') }}

),

daily_net as (

    select
        sku,
        warehouse_id,
        movement_date as date_day,
        sum(quantity) as net_change_qty,
        sum(case when movement_type = 'sale' then -quantity else 0 end) as sold_qty,
        sum(case when movement_type = 'receipt' then quantity else 0 end) as received_qty

    from movements
    group by sku, warehouse_id, movement_date

),

pairs as (

    select
        sku,
        warehouse_id,
        min(date_day) as first_date
    from daily_net
    group by sku, warehouse_id

),

spine as (

    select
        pairs.sku,
        pairs.warehouse_id,
        days.date_day
    from pairs
    inner join days
        on pairs.first_date <= days.date_day

),

balances as (

    select
        spine.sku,
        spine.warehouse_id,
        spine.date_day,
        coalesce(daily_net.net_change_qty, 0) as net_change_qty,
        coalesce(daily_net.sold_qty, 0) as sold_qty,
        coalesce(daily_net.received_qty, 0) as received_qty,
        sum(coalesce(daily_net.net_change_qty, 0)) over (
            partition by spine.sku, spine.warehouse_id
            order by spine.date_day
            rows between unbounded preceding and current row
        ) as on_hand_qty

    from spine
    left join daily_net
        on
            spine.sku = daily_net.sku
            and spine.warehouse_id = daily_net.warehouse_id
            and spine.date_day = daily_net.date_day

)

select * from balances
