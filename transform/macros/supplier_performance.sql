{#
    Supplier performance metrics, shared by mart_supplier_performance (per supplier) and
    mart_supplier_performance_quarterly (per supplier x quarter). `pos` must be a relation
    with one row per purchase order (see the `purchase_orders` CTE in those marts).
#}
{% macro supplier_performance_metrics() -%}
    count(*) as po_count,
    sum(case when is_received then 1 else 0 end) as received_po_count,
    sum(ordered_value_usd) as spend_usd,
    avg(case when is_received then case when is_on_time then 1.0 else 0.0 end end) as on_time_rate,
    avg(actual_lead_time_days) as lead_time_mean_days,
    stddev_samp(actual_lead_time_days) as lead_time_std_days,
    avg(case when is_received then quoted_lead_time_days end) as quoted_lead_time_mean_days,
    avg(actual_lead_time_days - quoted_lead_time_days) as quoted_vs_actual_gap_days,
    sum(quantity_received) / nullif(sum(case when is_received then quantity_ordered end), 0) as fill_rate,
    sum(case when is_short then 1 else 0 end) as short_shipment_count
{%- endmacro %}
