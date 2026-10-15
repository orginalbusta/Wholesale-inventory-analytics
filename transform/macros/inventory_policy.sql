{#
    Reorder-policy math (docs/04_dbt_spec.md). Kept in macros so the formulas are written
    once and the forecasting layer can feed them different demand inputs later.
#}

{# Safety stock covering both demand and lead-time variability:
   z * sqrt( L * sigma_d^2 + d^2 * sigma_L^2 ) #}
{% macro safety_stock(z, demand_mean, demand_std, lead_time_mean, lead_time_std) -%}
    {{ z }} * sqrt(
        {{ lead_time_mean }} * power({{ demand_std }}, 2)
        + power({{ demand_mean }}, 2) * power({{ lead_time_std }}, 2)
    )
{%- endmacro %}

{# Round a quantity up to a whole number of case packs. #}
{% macro round_up_to_case_pack(quantity, case_pack) -%}
    ceil({{ quantity }} / {{ case_pack }}) * {{ case_pack }}
{%- endmacro %}
