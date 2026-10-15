-- Grain: one row per stock location.

select
    cast(warehouse_id as varchar) as warehouse_id,
    cast(warehouse_name as varchar) as warehouse_name,
    cast(warehouse_type as varchar) as warehouse_type,
    cast(city as varchar) as city,
    cast(state as varchar) as state,
    cast(is_seasonal as boolean) as is_seasonal

from {{ ref('stg_erp__warehouses') }}
