---
title: Inventory health
---

<Alert status="warning">
<b>Synthetic data</b> · an ideal-state design, <b>not</b> the production system at Craftstones USA.
</Alert>

**ABC** ranks SKUs by the last 12 months of revenue (A = the SKUs that make up the first 80%). **XYZ** measures how steady weekly demand is (X = steady, Z = erratic). Together they set how much safety stock each SKU deserves.

## ABC/XYZ matrix

```sql matrix
select
    abc_class,
    xyz_class,
    count(*) as skus,
    sum(on_hand_value_usd) as on_hand_value_usd
from marts.inventory_health
group by 1, 2
order by 1, 2
```

<Heatmap data={matrix} x=xyz_class y=abc_class value=skus valueFmt=num0 title="Number of SKUs" />
<Heatmap data={matrix} x=xyz_class y=abc_class value=on_hand_value_usd valueFmt=usd0k title="Inventory value at cost" />

## Dead stock

Dead stock = stock on hand with no sale in the last 180 days: cash tied up on the shelf.

```sql dead_stock
select
    sku,
    '/sku/' || sku as sku_link,
    product_name,
    category,
    on_hand_qty,
    on_hand_value_usd,
    last_sale_date,
    days_since_last_sale,
    is_active
from marts.inventory_health
where is_dead_stock
order by on_hand_value_usd desc
```

```sql dead_by_category
select category, sum(on_hand_value_usd) as dead_stock_value_usd
from ${dead_stock}
group by 1
order by 2 desc
```

<BarChart data={dead_by_category} x=category y=dead_stock_value_usd yFmt=usd0k swapXY=true title="Dead-stock value by category" />

<DataTable data={dead_stock} rows=15 link=sku_link>
    <Column id=sku />
    <Column id=product_name title="Product" />
    <Column id=category />
    <Column id=on_hand_qty title="On hand" fmt=num0 />
    <Column id=on_hand_value_usd title="Value at cost" fmt=usd0 />
    <Column id=last_sale_date title="Last sale" />
    <Column id=days_since_last_sale title="Days since sale" fmt=num0 />
    <Column id=is_active title="Still sold" />
</DataTable>

## Days of supply

How long current stock lasts at the last 90 days' demand rate.

```sql days_of_supply
select
    case
        when avg_daily_demand_90d = 0 or avg_daily_demand_90d is null then '7. no recent demand'
        when days_of_supply = 0 then '1. out of stock'
        when days_of_supply <= 30 then '2. 1-30 days'
        when days_of_supply <= 90 then '3. 31-90 days'
        when days_of_supply <= 180 then '4. 91-180 days'
        when days_of_supply <= 365 then '5. 181-365 days'
        else '6. over a year'
    end as days_of_supply_bucket,
    count(*) as skus,
    sum(on_hand_value_usd) as on_hand_value_usd
from marts.inventory_health
group by 1
order by 1
```

<BarChart data={days_of_supply} x=days_of_supply_bucket y=skus title="SKUs by days of supply" />
<BarChart data={days_of_supply} x=days_of_supply_bucket y=on_hand_value_usd yFmt=usd0k title="Inventory value by days of supply" />
