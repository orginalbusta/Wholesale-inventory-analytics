"""Dagster code location for the Craftstones pipeline (Phase 6).

Implementation plan:
    Assets
      - simulate_day           runs generator in simulate-day mode
      - erp_raw / fred_raw     run ingestion.load_erp / ingestion.load_fred (depend on simulate_day)
      - craftstones_dbt_assets        @dbt_assets from transform/target/manifest.json via dagster-dbt
                               (DbtProject + DbtCliResource); upstream deps mapped from dbt sources
                               to erp_raw / fred_raw so lineage is end to end
      - source freshness       run `dbt source freshness` as an asset check
    Jobs and schedules
      - daily_pipeline_job     all assets
      - daily_schedule         ~06:00 America/Los_Angeles, default_status=STOPPED
    Asset checks
      - surface dbt tests as Dagster asset checks (dagster-dbt does this when building from the manifest)

Check the current dagster-dbt API before writing this; it has changed across releases.
"""

from dagster import Definitions

# TODO (Phase 6): replace with real assets, jobs, schedules, resources.
defs = Definitions()
