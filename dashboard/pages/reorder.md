---
title: Reorder recommendations
---

<Alert status="warning">
<b>Synthetic data</b> · an ideal-state design, <b>not</b> the production system at Craftstones USA.
</Alert>

Reorder points account for **both** demand variability and supplier lead-time variability, with a service level set by each SKU's ABC/XYZ class:

- safety stock = z × √( L × σ<sub>d</sub>² + d² × σ<sub>L</sub>² )
- reorder point = d × L + safety stock; reorder when on hand + on order ≤ reorder point
- suggested quantity = reorder point + 14 days of demand − position, rounded up to whole case packs

Demand (d, σ<sub>d</sub>) is the last 90 days of true demand, including orders lost to stockouts; lead time (L, σ<sub>L</sub>) is the supplier's *actual* history, not its quote.

```sql categories
select distinct category from marts.reorder_recommendations order by 1
```

```sql suppliers
select distinct supplier_id, supplier_name from marts.reorder_recommendations order by supplier_name
```

<Dropdown data={categories} name=category value=category title="Category" defaultValue="%">
    <DropdownOption value="%" valueLabel="All categories" />
</Dropdown>

<Dropdown data={suppliers} name=supplier value=supplier_id label=supplier_name title="Supplier" defaultValue="%">
    <DropdownOption value="%" valueLabel="All suppliers" />
</Dropdown>

<Dropdown name=abc title="ABC class" defaultValue="%">
    <DropdownOption value="%" valueLabel="All classes" />
    <DropdownOption value="A" />
    <DropdownOption value="B" />
    <DropdownOption value="C" />
</Dropdown>

```sql reorder
select
    sku,
    '/sku/detail/?id=' || sku as sku_link,
    product_name,
    category,
    supplier_name,
    abc_class || xyz_class as class,
    reorder_now,
    case when reorder_now then 'Yes' else '' end as reorder_label,
    suggested_order_qty,
    on_hand_qty,
    on_order_qty,
    reorder_point_qty,
    safety_stock_qty,
    demand_mean_daily,
    lead_time_mean_days,
    lead_time_std_days,
    target_service_level
from marts.reorder_recommendations
where category like '${inputs.category.value}'
    and supplier_id like '${inputs.supplier.value}'
    and abc_class like '${inputs.abc.value}'
order by reorder_now desc, abc_class, suggested_order_qty desc
```

```sql reorder_summary
select
    count(*) as skus,
    count(*) filter (where reorder_now) as skus_to_reorder
from ${reorder}
```

<BigValue data={reorder_summary} value=skus_to_reorder title="SKUs to reorder now" />
<BigValue data={reorder_summary} value=skus title="SKUs shown" />

Order qty is 0 when no order is needed. Click a row for the SKU's page: supplier, demand, lead times and the full calculation inputs.

<DataTable data={reorder} search=true rows=25 link=sku_link>
    <Column id=sku title="SKU" />
    <Column id=product_name title="Product" />
    <Column id=class title="Class" />
    <Column id=suggested_order_qty title="Order qty" fmt=num0 />
    <Column id=on_hand_qty title="On hand" fmt=num0 />
    <Column id=reorder_point_qty title="Reorder at" fmt=num0 />
</DataTable>
