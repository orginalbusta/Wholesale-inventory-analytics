-- Every service level in the ABC x XYZ policy must exist in the z-score lookup with the same
-- z-score, so the what-if page and the reorder mart agree at the default (policy) inputs.

select
    class_policy.abc_class,
    class_policy.xyz_class,
    class_policy.target_service_level,
    class_policy.z_score as policy_z_score,
    z_lookup.z_score as lookup_z_score
from {{ ref('abc_xyz_policy') }} as class_policy
left join {{ ref('service_level_z_scores') }} as z_lookup
    on class_policy.target_service_level = z_lookup.service_level
where z_lookup.z_score is null or abs(z_lookup.z_score - class_policy.z_score) > 0.0005
