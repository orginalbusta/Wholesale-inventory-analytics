-- Grain: one row per customer record, mapped to the surviving (canonical) record.
-- Resolves planted issue 1: the same business keyed twice ("Rock & Gem Shop" vs
-- "Rock and Gem Shop LLC"). Two records are the same business when they share
--   (a) a normalized name: lowercase, '&' -> 'and', punctuation removed, trailing
--       LLC / Inc / Co dropped; or
--   (b) a valid email, together with the same customer type and state (an email alone
--       could be a shared mailbox).
-- The canonical record is the earliest one (lowest ID: the ERP assigns IDs in creation order).

with

customers as (

    select * from {{ ref('stg_erp__customers') }}

),

name_step_1 as (

    select
        *,
        {{ regexp_replace_all("replace(lower(customer_name), '&', ' and ')", '[^a-z0-9 ]', ' ') }}
            as name_1
    from customers

),

name_step_2 as (

    select
        *,
        trim({{ regexp_replace_all('name_1', '[[:space:]]+', ' ') }}) as name_2
    from name_step_1

),

match_keys as (

    select
        customer_id,
        customer_name,
        {{ regexp_replace_all('name_2', '( (llc|inc|co))+$', '') }} as match_name,
        case
            when is_email_valid then contact_email || '|' || customer_type || '|' || state
        end as match_email

    from name_step_2

),

candidates as (

    select
        customer_id,
        customer_name,
        match_name,
        match_email,
        min(customer_id) over (partition by match_name) as first_by_name,
        case
            when match_email is not null
                then min(customer_id) over (partition by match_email)
        end as first_by_email

    from match_keys

),

resolved as (

    select
        customer_id,
        customer_name,
        least(first_by_name, coalesce(first_by_email, first_by_name)) as canonical_customer_id,
        case
            when first_by_name < customer_id and first_by_email < customer_id then 'name+email'
            when first_by_name < customer_id then 'name'
            when first_by_email < customer_id then 'email'
        end as match_rule

    from candidates

)

select
    customer_id,
    canonical_customer_id,
    customer_id <> canonical_customer_id as is_duplicate_record,
    match_rule,
    customer_name
from resolved
