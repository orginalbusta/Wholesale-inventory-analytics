-- Purchase order lines per SKU: everything still open plus the trailing 12 months, for the SKU pages.
select
    sku,
    po_id,
    supplier_id,
    order_date,
    expected_arrival_date,
    actual_arrival_date,
    po_status,
    quantity_ordered,
    quantity_received,
    open_quantity,
    quoted_lead_time_days,
    actual_lead_time_days,
    days_late,
    is_on_time
from marts.fct_purchase_order_lines
where
    not is_received
    or order_date > (select max(order_date) from marts.fct_purchase_order_lines) - 365
