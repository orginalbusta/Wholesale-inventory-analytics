-- Total inventory value by category per day (summed across warehouses), at the cost in effect that day.
select
    i.date_day,
    p.category,
    sum(i.on_hand_value_usd) as on_hand_value_usd
from marts.fct_inventory_daily as i
inner join marts.dim_products as p using (sku)
group by 1, 2
