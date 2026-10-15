-- True demand per SKU per week (fulfilled + unfilled), trailing 12 months, for the SKU pages.
-- Return lines are excluded: they are not demand.
select
    sku,
    date_trunc('week', order_date) as week_start_date,
    sum(quantity_ordered) as ordered_qty,
    sum(quantity_fulfilled) as fulfilled_qty,
    sum(quantity_unfilled) as unfilled_qty
from marts.fct_order_lines
where
    not is_return_line
    and order_date > (select max(order_date) from marts.fct_order_lines) - 365
group by 1, 2
