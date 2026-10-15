-- Flags customer records that share an email address: likely the same business keyed twice
-- (planted issue 1). Warn only: duplicates are resolved in int_customers__deduplicated.
{{ config(severity='warn') }}

select
    contact_email,
    count(*) as n_records
from {{ ref('stg_erp__customers') }}
where contact_email is not null
group by contact_email
having count(*) > 1
