"""The dashboard's what-if page recomputes the reorder policy in the browser. These tests run the
page's own SQL (read from dashboard/pages/what-if.md) against a real small warehouse and check:

- at the page's default inputs it reproduces mart_reorder_recommendations exactly;
- moving each input changes the results in the expected direction;
- the SKU drill-down page's main query returns one row for every SKU the index page links to.

Evidence serves each dashboard/sources/marts/<name>.sql query as the table `marts.<name>`; the
tests recreate those as views `evidence.<name>` in the test warehouse and point the page SQL there.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from generator.config import REPO_ROOT

DASHBOARD = REPO_ROOT / "dashboard"
WHAT_IF_PAGE = DASHBOARD / "pages" / "what-if.md"
SKU_PAGE = DASHBOARD / "pages" / "sku" / "detail.md"
SKU_INDEX = DASHBOARD / "pages" / "sku" / "index.md"


def page_queries(page: Path) -> dict[str, str]:
    """Named ```sql blocks in an Evidence page."""
    text = page.read_text(encoding="utf-8")
    return {name: sql for name, sql in re.findall(r"```sql (\w+)\n(.*?)```", text, re.DOTALL)}


def page_defaults(page: Path) -> dict[str, str]:
    """defaultValue of every Slider and Dropdown on the page, by input name."""
    text = page.read_text(encoding="utf-8")
    defaults = {}
    for tag in re.findall(r"<(?:Slider|Dropdown)\b[^>]*>", text):
        name = re.search(r"\bname=(\w+)", tag).group(1)
        defaults[name] = re.search(r'\bdefaultValue="?([\w.]+)"?', tag).group(1)
    return defaults


def to_test_schema(page_sql: str) -> str:
    """Page queries read Evidence sources as marts.<name>; in the tests they live in evidence.<name>."""
    return page_sql.replace("marts.", "evidence.")


def fill_inputs(sql: str, values: dict[str, str]) -> str:
    """Substitute Evidence ${inputs.x} / ${inputs.x.value} placeholders."""
    for name, value in values.items():
        sql = sql.replace(f"${{inputs.{name}.value}}", value).replace(f"${{inputs.{name}}}", value)
    assert "${" not in sql, f"unfilled placeholder in: {sql}"
    return sql


@pytest.fixture(scope="module")
def dashboard_db(built) -> duckdb.DuckDBPyConnection:
    """The test warehouse with every dashboard source as a view evidence.<name>."""
    # Same (read-write) configuration as dbt-duckdb's in-process connection; see dbt_helpers.query.
    con = duckdb.connect(str(built["root"] / "warehouse.duckdb"))
    con.execute("create schema if not exists evidence")
    for source in sorted((DASHBOARD / "sources" / "marts").glob("*.sql")):
        sql = source.read_text(encoding="utf-8")
        con.execute(f"create or replace view evidence.{source.stem} as {sql}")
    yield con
    con.close()


def run_what_if(con: duckdb.DuckDBPyConnection, **overrides: str) -> pd.DataFrame:
    inputs = {**page_defaults(WHAT_IF_PAGE), **overrides}
    sql = fill_inputs(to_test_schema(page_queries(WHAT_IF_PAGE)["whatif"]), inputs)
    return con.execute(sql).df().set_index("sku").sort_index()


def test_defaults_reproduce_the_mart_exactly(dashboard_db):
    page = run_what_if(dashboard_db)
    mart = (
        dashboard_db.execute("select * from marts.mart_reorder_recommendations")
        .df()
        .set_index("sku")
        .sort_index()
    )
    assert list(page.index) == list(mart.index)

    pd.testing.assert_series_equal(
        page["scenario_service_level"], mart["target_service_level"], check_names=False
    )
    for scenario, current in [
        ("scenario_safety_stock_qty", "safety_stock_qty"),
        ("scenario_reorder_point_qty", "reorder_point_qty"),
        ("scenario_suggested_order_qty", "suggested_order_qty"),
    ]:
        pd.testing.assert_series_equal(
            page[scenario], mart[current], check_names=False, rtol=1e-12, atol=1e-9
        )
    assert (page["scenario_reorder_now"] == mart["reorder_now"]).all()
    assert mart["reorder_now"].any(), "fixture should have SKUs to reorder"


def test_page_defaults_match_the_dbt_policy(dashboard_db):
    defaults = page_defaults(WHAT_IF_PAGE)
    review_days = dashboard_db.execute(
        "select distinct review_period_days from marts.mart_reorder_recommendations"
    ).fetchall()
    assert review_days == [(int(defaults["review_period"]),)]
    assert defaults["lead_time_buffer"] == "0"
    assert {defaults[k] for k in ("sl_a", "sl_b", "sl_c")} == {"policy"}


def test_higher_service_level_raises_a_class_safety_stock(dashboard_db):
    base = run_what_if(dashboard_db)
    high = run_what_if(dashboard_db, sl_a="0.999")
    a_class = base["abc_class"] == "A"
    assert (
        high.loc[a_class, "scenario_safety_stock_qty"]
        >= base.loc[a_class, "scenario_safety_stock_qty"]
    ).all()
    assert (
        high.loc[a_class, "scenario_safety_stock_qty"].sum()
        > base.loc[a_class, "scenario_safety_stock_qty"].sum()
    )
    # Other classes are untouched.
    pd.testing.assert_series_equal(
        high.loc[~a_class, "scenario_safety_stock_qty"], base.loc[~a_class, "scenario_safety_stock_qty"]
    )  # fmt: skip


def test_lead_time_buffer_raises_reorder_points(dashboard_db):
    base = run_what_if(dashboard_db)
    buffered = run_what_if(dashboard_db, lead_time_buffer="10")
    assert (buffered["scenario_reorder_point_qty"] >= base["scenario_reorder_point_qty"]).all()
    assert buffered["scenario_reorder_now"].sum() >= base["scenario_reorder_now"].sum()


def test_longer_review_period_orders_more(dashboard_db):
    base = run_what_if(dashboard_db)
    longer = run_what_if(dashboard_db, review_period="45")
    pd.testing.assert_series_equal(longer["scenario_reorder_now"], base["scenario_reorder_now"])
    assert (longer["scenario_suggested_order_qty"] >= base["scenario_suggested_order_qty"]).all()
    assert longer["scenario_suggested_order_qty"].sum() > base["scenario_suggested_order_qty"].sum()


def test_every_linked_sku_page_has_data(dashboard_db):
    skus = dashboard_db.execute(to_test_schema(page_queries(SKU_INDEX)["skus"])).df()["sku"]
    detail_sql = to_test_schema(page_queries(SKU_PAGE)["sku_info"])
    rows_per_sku = {
        len(dashboard_db.execute(detail_sql.replace("${sku_id}", sku)).fetchall()) for sku in skus
    }
    assert len(skus) > 0
    assert rows_per_sku == {1}
