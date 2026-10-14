"""Generator tests (Phase 1). See invariants in generator/generate.py and docs/05_roadmap.md.

Planned tests:
    - test_deterministic_output: two runs with the same seed and scale produce identical file hashes
    - test_volumes_within_tolerance: row counts within ±25% of config targets
    - test_true_inventory_never_negative
    - test_fulfilled_not_more_than_ordered
    - test_stockouts_and_dead_stock_exist
    - test_pareto_revenue_concentration: top 20% of SKUs ≈ 75–80% of revenue
    - test_seasonality_visible: Nov Jewelry Components revenue > Jul
    - test_planted_issues_at_configured_rates
    - test_simulate_day_appends_one_day
"""

import pytest


@pytest.mark.skip(reason="Phase 1 not implemented yet")
def test_placeholder() -> None:
    pass
