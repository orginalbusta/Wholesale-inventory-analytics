{#
    Normalize SKU variants (e.g. `amt-pls-0042`, `AMTPLS0042`, ` Amt-Pls-0042 `)
    to the canonical `AMT-PLS-0042` format. See docs/03_data_spec.md, planted issue 3.

    TODO (Phase 3): confirm this works on both DuckDB and Snowflake; add a dbt unit test.
#}
{% macro normalize_sku(column_name) -%}
    {%- set stripped = "regexp_replace(upper(trim(" ~ column_name ~ ")), '[^A-Z0-9]', '', 'g')" -%}
    {%- if target.type == 'snowflake' -%}
        {%- set stripped = "regexp_replace(upper(trim(" ~ column_name ~ ")), '[^A-Z0-9]', '')" -%}
    {%- endif -%}
    case
        when length({{ stripped }}) = 10
            then substr({{ stripped }}, 1, 3) || '-' || substr({{ stripped }}, 4, 3) || '-' || substr({{ stripped }}, 7, 4)
        else upper(trim({{ column_name }}))
    end
{%- endmacro %}
