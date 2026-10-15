-- A supplier may over-ship slightly, but never more than 5% above the ordered quantity.

select
    po_line_id,
    quantity_ordered,
    quantity_received
from {{ ref('fct_purchase_order_lines') }}
where quantity_received > quantity_ordered * 1.05
