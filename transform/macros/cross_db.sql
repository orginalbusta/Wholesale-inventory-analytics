{#
    Small cross-database helpers so models stay warehouse-agnostic (DuckDB and Snowflake).
    dbt's own cross-db macros (dbt.safe_cast, dbt.dateadd, ...) cover the rest.
#}

{# Replace every match of a regex. DuckDB needs the 'g' flag; Snowflake replaces all by default. #}
{% macro regexp_replace_all(expression, pattern, replacement) -%}
    {{ return(adapter.dispatch('regexp_replace_all', 'craftstones')(expression, pattern, replacement)) }}
{%- endmacro %}

{% macro duckdb__regexp_replace_all(expression, pattern, replacement) -%}
    regexp_replace({{ expression }}, '{{ pattern }}', '{{ replacement }}', 'g')
{%- endmacro %}

{% macro default__regexp_replace_all(expression, pattern, replacement) -%}
    regexp_replace({{ expression }}, '{{ pattern }}', '{{ replacement }}')
{%- endmacro %}


{# True when the whole string matches the pattern. #}
{% macro regexp_full_match(expression, pattern) -%}
    {{ return(adapter.dispatch('regexp_full_match', 'craftstones')(expression, pattern)) }}
{%- endmacro %}

{% macro duckdb__regexp_full_match(expression, pattern) -%}
    regexp_full_match({{ expression }}, '{{ pattern }}')
{%- endmacro %}

{% macro default__regexp_full_match(expression, pattern) -%}
    regexp_like({{ expression }}, '{{ pattern }}')
{%- endmacro %}


{# Trim, lowercase and collapse internal whitespace: '  Polished  Stones ' -> 'polished stones'. #}
{% macro normalize_label(expression) -%}
    {{ regexp_replace_all('lower(trim(' ~ expression ~ '))', '[[:space:]]+', ' ') }}
{%- endmacro %}
