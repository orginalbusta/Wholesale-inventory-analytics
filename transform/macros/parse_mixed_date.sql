{#
    Parse a string column holding either `YYYY-MM-DD` or `MM/DD/YYYY`.
    See docs/03_data_spec.md, planted issue 8. Adapter-dispatched so it works on
    DuckDB and Snowflake.
#}
{% macro parse_mixed_date(column_name) -%}
    {{ return(adapter.dispatch('parse_mixed_date', 'craftstones')(column_name)) }}
{%- endmacro %}

{% macro duckdb__parse_mixed_date(column_name) -%}
    coalesce(
        try_strptime({{ column_name }}, '%Y-%m-%d'),
        try_strptime({{ column_name }}, '%m/%d/%Y')
    )::date
{%- endmacro %}

{% macro snowflake__parse_mixed_date(column_name) -%}
    coalesce(
        try_to_date({{ column_name }}, 'YYYY-MM-DD'),
        try_to_date({{ column_name }}, 'MM/DD/YYYY')
    )
{%- endmacro %}

{% macro default__parse_mixed_date(column_name) -%}
    cast({{ column_name }} as date)
{%- endmacro %}
