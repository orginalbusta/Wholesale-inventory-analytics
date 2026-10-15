-- On every count date, the end-of-day ledger balance must equal the counted quantity:
-- each variance must have been posted as an adjustment (counts are the day's last event).

select
    counts.count_id,
    counts.sku,
    counts.count_date,
    counts.counted_qty,
    balances.on_hand_qty
from {{ ref('stg_erp__cycle_counts') }} as counts
inner join {{ ref('fct_inventory_daily') }} as balances
    on
        counts.sku = balances.sku
        and counts.warehouse_id = balances.warehouse_id
        and counts.count_date = balances.date_day
where abs(counts.counted_qty - balances.on_hand_qty) > 0.0001
