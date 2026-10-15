-- Grain: one row per service level. The z-scores the dashboard's what-if page can apply, from the
-- same seed table dbt would use, so the page never computes an inverse normal in the browser.

with

levels as (

    select * from {{ ref('service_level_z_scores') }}

)

select
    cast(service_level as double) as service_level,
    cast(z_score as double) as z_score

from levels
