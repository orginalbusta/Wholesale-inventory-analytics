-- Remove everything snowflake/setup.sql created. Run as ACCOUNTADMIN when you're done with
-- the Snowflake target (or just let the trial expire). Irreversible: drops all loaded data.

use role accountadmin;

drop database if exists craftstones_analytics;
drop user if exists dbt_svc;
drop warehouse if exists craftstones_wh;
drop resource monitor if exists craftstones_monitor;
drop role if exists transformer;
