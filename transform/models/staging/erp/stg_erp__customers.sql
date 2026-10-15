-- Grain: one row per customer record (latest version). Duplicate business records
-- (planted issue 1) are kept here and resolved in int_customers__deduplicated.
-- Handles planted issue 7: emails are trimmed and lowercased; malformed ones are flagged.

with

source as (

    select * from {{ source('erp', 'customers') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by customer_id
        order by updated_at desc, _extracted_at desc
    ) = 1

),

renamed as (

    select
        customer_id,
        trim(customer_name) as customer_name,
        lower(trim(customer_type)) as customer_type,
        nullif(lower(trim(contact_email)), '') as contact_email,
        upper(trim(state)) as state,
        upper(trim(credit_terms)) as credit_terms,
        upper(trim(sales_rep_id)) as sales_rep_id,
        cast(first_order_date as date) as first_order_date,
        cast(created_at as timestamp) as created_at,
        cast(updated_at as timestamp) as updated_at,
        cast(_extracted_at as timestamp) as extracted_at

    from deduplicated

),

flagged as (

    select
        *,
        case
            when contact_email is null then null
            else {{ regexp_full_match('contact_email', '[a-z0-9._%+-]+@[a-z0-9.-]+[.][a-z]{2,}') }}
        end as is_email_valid

    from renamed

)

select * from flagged
