{#
    Use the custom schema name as-is (e.g. `staging`, `marts`) instead of dbt's
    default `<target_schema>_<custom_schema>`. Keeps warehouse schemas clean for the
    dashboard and docs.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
