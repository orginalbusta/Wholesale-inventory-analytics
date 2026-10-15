-- Selectable service levels and their z-scores for the what-if page (same seed dbt uses).
select
    service_level,
    z_score,
    printf('%.1f%%', service_level * 100) as service_level_label
from marts.dim_service_levels
