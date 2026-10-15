-- Gem show windows, for shading charts.
select
    show_name,
    min(date_day) as start_date,
    max(date_day) as end_date
from marts.dim_date
where is_show_day
group by show_name, show_warehouse_id, extract(year from date_day)
