-- One-time Snowflake setup for the optional `snowflake` target (Phase 8).
-- Run once, as ACCOUNTADMIN, in a Snowsight SQL worksheet ("Run All").
-- Full walkthrough, including the key pair: snowflake/README.md.
--
-- Before running, change the two values marked "CHANGE ME":
--   1. the credit cap on the resource monitor (step 2)
--   2. the RSA public key for the service user (step 4)
--
-- Creates:
--   CRAFTSTONES_WH          X-Small warehouse, suspends after 60s idle, starts suspended
--   CRAFTSTONES_MONITOR     resource monitor: notify at 50%, suspend at 90% and 100% of the cap
--   TRANSFORMER             role that owns everything the pipeline creates
--   CRAFTSTONES_ANALYTICS   database (dlt and dbt create their schemas inside it)
--   DBT_SVC                 service user (key-pair auth only, no password) used by dbt and dlt
--
-- Undo everything with snowflake/teardown.sql.

use role accountadmin;


-- 1. Warehouse: the smallest size, and it stops billing 60 seconds after the last query.
create warehouse if not exists craftstones_wh
    warehouse_size = 'XSMALL'
    auto_suspend = 60
    auto_resume = true
    initially_suspended = true
    comment = 'Craftstones portfolio project (synthetic data): dbt + dlt runs';


-- 2. Hard cap on spend. An X-Small warehouse uses 1 credit per hour of running time;
--    a medium-scale build takes minutes, so 10 credits is plenty. Suspended warehouses cost nothing.
create or replace resource monitor craftstones_monitor
    with
        credit_quota = 10  -- CHANGE ME if you want a different cap (credits per month)
        frequency = monthly
        start_timestamp = immediately
    triggers
        on 50 percent do notify
        on 90 percent do suspend
        on 100 percent do suspend_immediate;

alter warehouse craftstones_wh set resource_monitor = craftstones_monitor;


-- 3. Role and database. TRANSFORMER owns the database, so dlt and dbt can create the
--    raw_erp, raw_fred, staging, intermediate, marts, seeds and snapshots schemas themselves.
create role if not exists transformer
    comment = 'Owns the Craftstones portfolio database; used by dbt and dlt';
grant role transformer to role sysadmin;  -- keep the standard role hierarchy

grant usage, operate on warehouse craftstones_wh to role transformer;

create database if not exists craftstones_analytics
    comment = 'Craftstones portfolio project. All data is synthetic.';
grant ownership on database craftstones_analytics to role transformer copy current grants;
grant ownership on schema craftstones_analytics.public to role transformer copy current grants;

-- Let your own login use the role too, so you can browse the results in Snowsight.
set my_user = '"' || current_user() || '"';
grant role transformer to user identifier($my_user);


-- 4. Service user for dbt and dlt: key-pair authentication only (TYPE = SERVICE has no password
--    and no MFA prompt). Paste the PUBLIC key (one line, without the BEGIN/END lines) below.
--    snowflake/README.md shows the command that prints it in exactly that form.
create user if not exists dbt_svc
    type = service
    default_role = transformer
    default_warehouse = craftstones_wh
    default_namespace = craftstones_analytics
    comment = 'Craftstones portfolio project: dbt and dlt (key-pair auth)';

alter user dbt_svc set rsa_public_key = 'PASTE_YOUR_PUBLIC_KEY_HERE';  -- CHANGE ME

grant role transformer to user dbt_svc;


-- 5. Checks. Each should return one row; DESCRIBE USER should show a value for
--    RSA_PUBLIC_KEY_FP (the key's fingerprint).
show warehouses like 'CRAFTSTONES_WH';
show resource monitors like 'CRAFTSTONES_MONITOR';
show grants to role transformer;
describe user dbt_svc;
