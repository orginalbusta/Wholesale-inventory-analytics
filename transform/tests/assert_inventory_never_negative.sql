-- Stock on hand can never go below zero at the end of any day.

select
    sku,
    warehouse_id,
    date_day,
    on_hand_qty
from {{ ref('fct_inventory_daily') }}
where on_hand_qty < 0
