{#
    Normalize SKU variants (e.g. `amt-pls-0042`, `AMTPLS0042`, ` Amt_Pls_0042 `) to the
    canonical `AMT-PLS-0042` format: uppercase, strip non-alphanumerics, and re-insert the
    dashes when exactly 10 characters remain. Anything else is returned trimmed and
    uppercased, so unknown codes stay visible (and fail the relationships test).
    See docs/03_data_spec.md, planted issue 3. Unit-tested in _erp__models.yml.
#}
{% macro normalize_sku(column_name) -%}
    {%- set stripped = regexp_replace_all('upper(trim(' ~ column_name ~ '))', '[^A-Z0-9]', '') -%}
    case
        when length({{ stripped }}) = 10
            then
                substr({{ stripped }}, 1, 3) || '-'
                || substr({{ stripped }}, 4, 3) || '-'
                || substr({{ stripped }}, 7, 4)
        else upper(trim({{ column_name }}))
    end
{%- endmacro %}
