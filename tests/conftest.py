"""Shared fixtures. `built` is a small warehouse (backfill + one simulate-day) built once per
test session and fully transformed by `dbt build`; dbt tests use it read-only."""

from __future__ import annotations

import pytest
from dbt_helpers import generate_and_load, planted_issues, run_dbt


@pytest.fixture(scope="session")
def built(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("dbt_built")
    generate_and_load(root, simulated_days=1)
    result = run_dbt(root, "build")
    return {**result, "root": root, "issues": planted_issues(root)}
