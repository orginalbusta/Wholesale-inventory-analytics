---
title: All SKUs
---

<Alert status="warning">
<b>Synthetic data</b> · an ideal-state design, <b>not</b> the production system at Craftstones USA.
</Alert>

Every SKU (including discontinued ones still holding stock) has its own page with stock history, demand, stockouts, purchase orders and its supplier's scorecard. Click a row to open one.

```sql skus
select
    sku,
    product_name,
    category,
    supplier_name,
    abc_class || xyz_class as class,
    is_active,
    is_dead_stock,
    on_hand_qty,
    '/sku/' || sku as sku_link
from marts.inventory_health as h
left join (select distinct supplier_id, supplier_name from marts.supplier_performance) using (supplier_id)
order by sku
```

<DataTable data={skus} search=true rows=25 link=sku_link>
    <Column id=sku />
    <Column id=product_name title="Product" />
    <Column id=category title="Category" />
    <Column id=supplier_name title="Supplier" />
    <Column id=class title="ABC/XYZ" />
    <Column id=is_active title="Active" />
    <Column id=is_dead_stock title="Dead stock" />
    <Column id=on_hand_qty title="On hand" fmt=num0 />
</DataTable>
