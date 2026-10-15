-- Stock on hand per SKU per day (all warehouses), trailing 12 months, for the SKU drill-down pages.
select
    sku,
    date_day,
    sum(on_hand_qty) as on_hand_qty,
    sum(on_hand_value_usd) as on_hand_value_usd
from marts.fct_inventory_daily
where date_day > (select max(date_day) from marts.fct_inventory_daily) - 365
group by 1, 2
