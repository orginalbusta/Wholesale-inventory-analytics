-- Grain: one row per FRED series per date. FRED marks missing values with '.' (API) or
-- an empty string (CSV download); those rows are dropped and values cast to numeric.
-- If FRED was unreachable on the first load, raw_fred.observations doesn't exist yet;
-- the model then returns no rows instead of breaking the build.

{%- set observations = source('fred', 'observations') -%}
{%- set source_exists = true -%}
{%- if execute -%}
    {%- set source_exists = adapter.get_relation(
        database=observations.database,
        schema=observations.schema,
        identifier=observations.identifier,
    ) is not none -%}
{%- endif %}

with

source as (

    {% if source_exists -%}
        select
            series_id,
            date as observation_date,
            value as raw_value,
            fetched_via
        from {{ observations }}
    {%- else -%}
        select
            cast(null as {{ dbt.type_string() }}) as series_id,
            cast(null as date) as observation_date,
            cast(null as {{ dbt.type_string() }}) as raw_value,
            cast(null as {{ dbt.type_string() }}) as fetched_via
        where 1 = 0
    {%- endif %}

),

renamed as (

    select
        upper(trim(series_id)) as series_id,
        cast(observation_date as date) as observation_date,
        {{ dbt.safe_cast('raw_value', dbt.type_numeric()) }} as observation_value,
        fetched_via

    from source
    where trim(raw_value) not in ('.', '')

)

select * from renamed
