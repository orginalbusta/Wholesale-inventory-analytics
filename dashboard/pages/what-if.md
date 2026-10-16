---
title: What-if reorder policy
---

<Alert status="warning">
<b>Synthetic data</b> · an ideal-state design, <b>not</b> the production system at Craftstones USA.
</Alert>

The [reorder recommendations](/reorder) use one policy: a service level per ABC/XYZ class, actual supplier lead times, and orders that cover 14 days beyond the reorder point. Change the policy below and every SKU's safety stock, reorder point and order quantity is recalculated in your browser with the same formulas as the dbt model.

**The trade-off:** a higher service level or a longer lead-time buffer means fewer stockouts, but more cash sitting in safety stock. A longer review period means fewer, larger orders.

```sql service_levels
select service_level, service_level_label from marts.service_levels order by service_level
```

<Dropdown data={service_levels} name=sl_a value=service_level label=service_level_label title="A-class service level" defaultValue="policy">
    <DropdownOption value="policy" valueLabel="Current policy (95-98% by XYZ)" />
</Dropdown>

<Dropdown data={service_levels} name=sl_b value=service_level label=service_level_label title="B-class service level" defaultValue="policy">
    <DropdownOption value="policy" valueLabel="Current policy (90-95% by XYZ)" />
</Dropdown>

<Dropdown data={service_levels} name=sl_c value=service_level label=service_level_label title="C-class service level" defaultValue="policy">
    <DropdownOption value="policy" valueLabel="Current policy (85-90% by XYZ)" />
</Dropdown>

Lead-time buffer: days added to every supplier's mean lead time. Review period: days of demand each order covers beyond the reorder point.

<Slider name=lead_time_buffer title="Lead-time buffer (days)" min=0 max=30 step=1 defaultValue=0 size=large />

<Slider name=review_period title="Review period (days)" min=7 max=60 step=1 defaultValue=14 size=large />

```sql whatif
-- Same formulas as mart_reorder_recommendations, with the policy inputs above:
--   safety stock  = z * sqrt(L * sigma_d^2 + d^2 * sigma_L^2), L = mean lead time + buffer
--   reorder point = d * L + safety stock; reorder when on hand + on order <= reorder point
--   order qty     = reorder point + d * review period - position, rounded up to case packs
with

choices as (

    select
        r.*,
        case r.abc_class
            when 'A' then '${inputs.sl_a.value}'
            when 'B' then '${inputs.sl_b.value}'
            else '${inputs.sl_c.value}'
        end as service_level_choice
    from marts.reorder_recommendations as r

),

scenario_inputs as (

    select
        c.*,
        case
            when c.service_level_choice = 'policy' then c.target_service_level
            else try_cast(c.service_level_choice as double)
        end as scenario_service_level,
        case
            when c.service_level_choice = 'policy' then c.z_score
            else levels.z_score
        end as scenario_z_score,
        c.lead_time_mean_days + ${inputs.lead_time_buffer} as scenario_lead_time_days
    from choices as c
    left join marts.service_levels as levels
        on c.service_level_choice <> 'policy'
        and levels.service_level = try_cast(c.service_level_choice as double)

),

scenario_policy as (

    select
        *,
        scenario_z_score * sqrt(
            scenario_lead_time_days * power(demand_std_daily, 2)
            + power(demand_mean_daily, 2) * power(lead_time_std_days, 2)
        ) as scenario_safety_stock_qty
    from scenario_inputs

),

scenario_reorder as (

    select
        *,
        demand_mean_daily * scenario_lead_time_days + scenario_safety_stock_qty
            as scenario_reorder_point_qty
    from scenario_policy

),

scenario as (

    select
        *,
        inventory_position <= scenario_reorder_point_qty and demand_mean_daily > 0
            as scenario_reorder_now,
        scenario_reorder_point_qty + demand_mean_daily * ${inputs.review_period}
            - inventory_position as scenario_raw_order_qty
    from scenario_reorder

)

select
    sku,
    product_name,
    category,
    supplier_name,
    abc_class,
    xyz_class,
    abc_class || xyz_class as class,
    unit_cost_usd,
    on_hand_qty,
    on_order_qty,
    inventory_position,
    demand_mean_daily,
    target_service_level,
    safety_stock_qty,
    reorder_point_qty,
    reorder_now,
    suggested_order_qty,
    scenario_service_level,
    scenario_safety_stock_qty,
    scenario_reorder_point_qty,
    scenario_reorder_now,
    case
        when scenario_reorder_now
            then ceil(greatest(scenario_raw_order_qty, 0) / case_pack_qty) * case_pack_qty
        else 0
    end as scenario_suggested_order_qty,
    '/sku/' || sku as sku_link
from scenario
```

```sql whatif_totals
select
    count(*) filter (where scenario_reorder_now) as scenario_skus_to_reorder,
    count(*) filter (where scenario_reorder_now) - count(*) filter (where reorder_now)
        as skus_to_reorder_change,
    sum(scenario_suggested_order_qty * unit_cost_usd) as scenario_order_value_usd,
    sum(scenario_suggested_order_qty * unit_cost_usd) - sum(suggested_order_qty * unit_cost_usd)
        as order_value_change_usd,
    sum(scenario_safety_stock_qty * unit_cost_usd) as scenario_safety_stock_value_usd,
    sum(scenario_safety_stock_qty * unit_cost_usd) - sum(safety_stock_qty * unit_cost_usd)
        as safety_stock_value_change_usd
from ${whatif}
```

```sql whatif_by_class
select abc_class, 'Current policy' as policy, sum(safety_stock_qty * unit_cost_usd) as safety_stock_value_usd
from ${whatif}
group by 1
union all
select abc_class, 'Scenario' as policy, sum(scenario_safety_stock_qty * unit_cost_usd) as safety_stock_value_usd
from ${whatif}
group by 1
order by abc_class, policy
```

```sql whatif_changes
select
    sku,
    sku_link,
    product_name,
    supplier_name,
    class,
    target_service_level,
    scenario_service_level,
    reorder_now,
    scenario_reorder_now,
    case when scenario_reorder_now then 'Yes' else '' end as scenario_reorder_label,
    suggested_order_qty,
    scenario_suggested_order_qty,
    scenario_suggested_order_qty - suggested_order_qty as order_qty_change,
    safety_stock_qty,
    scenario_safety_stock_qty,
    (scenario_safety_stock_qty - safety_stock_qty) * unit_cost_usd as safety_stock_value_change_usd
from ${whatif}
order by scenario_reorder_now desc, abs(scenario_suggested_order_qty - suggested_order_qty) desc, sku
```

## Scenario vs. current policy

Each card shows the scenario, with the change against the current policy underneath.

<BigValue data={whatif_totals} value=scenario_skus_to_reorder title="SKUs to reorder now" comparison=skus_to_reorder_change comparisonTitle="vs. current policy" comparisonFmt=num0 />
<BigValue data={whatif_totals} value=scenario_order_value_usd title="Order value now" fmt=usd0k comparison=order_value_change_usd comparisonTitle="vs. current policy" comparisonFmt=usd0k />
<BigValue data={whatif_totals} value=scenario_safety_stock_value_usd title="Cash in safety stock" fmt=usd0k comparison=safety_stock_value_change_usd comparisonTitle="vs. current policy" comparisonFmt=usd0k downIsGood=true />

<BarChart
    data={whatif_by_class}
    x=abc_class
    y=safety_stock_value_usd
    series=policy
    type=grouped
    yFmt=usd0k
    title="Cash in safety stock by ABC class"
/>

## Every SKU under the scenario

Changes are against the current policy. Click a row to open the SKU's page.

<DataTable data={whatif_changes} search=true rows=25 link=sku_link>
    <Column id=sku title="SKU" />
    <Column id=product_name title="Product" />
    <Column id=scenario_reorder_label title="Reorder" />
    <Column id=scenario_suggested_order_qty title="Order qty" fmt=num0 />
    <Column id=order_qty_change title="Qty change" fmt=num0 contentType=delta />
    <Column id=safety_stock_value_change_usd title="Cash change" fmt=usd0 contentType=delta />
</DataTable>

<Details title="How this page works">

The page reads `mart_reorder_recommendations`, which exposes every input of the reorder calculation (demand mean and standard deviation, lead-time mean and standard deviation, on hand, on order, case pack, unit cost). The service-level z-scores come from the `dim_service_levels` mart, built from the same seed dbt uses. With every control at its default, the page reproduces the mart exactly; a pytest (`tests/test_dashboard_whatif.py`) checks that on every CI run.

Cash figures value stock at current unit cost. Lead-time buffer and review period apply to every SKU.

</Details>
