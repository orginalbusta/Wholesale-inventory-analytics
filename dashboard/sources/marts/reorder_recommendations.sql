-- Reorder recommendations, with product and supplier names for the table.
select
    r.*,
    p.product_name,
    s.supplier_name
from marts.mart_reorder_recommendations as r
left join marts.dim_products as p using (sku)
left join marts.dim_suppliers as s on r.supplier_id = s.supplier_id
