"""scripts/dbt_failure_summary.py reports failed dbt nodes readably."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dbt_failure_summary import report  # noqa: E402


def write_results(path: Path, results: list[dict]) -> Path:
    path.write_text(json.dumps({"results": results}), encoding="utf-8")
    return path


def test_lists_failed_nodes_and_skipped_count(tmp_path):
    results = write_results(
        tmp_path / "run_results.json",
        [
            {"unique_id": "model.craftstones.stg_a", "status": "success", "message": "OK"},
            {
                "unique_id": "model.craftstones.stg_b",
                "status": "error",
                "message": 'Binder Error: column "x" not found | details',
            },
            {
                "unique_id": "test.craftstones.not_null_b_id.abc",
                "status": "fail",
                "message": "Got 3 results",
            },
            {"unique_id": "model.craftstones.int_c", "status": "skipped", "message": None},
        ],
    )
    text = report(results)
    assert "2 node(s) failed" in text
    assert "`stg_b`" in text and "`not_null_b_id.abc`" in text
    assert "stg_a" not in text
    assert "\\|" in text  # pipes in messages can't break the markdown table
    assert "1 downstream node(s) were skipped" in text


def test_explains_a_failure_before_any_node_ran(tmp_path):
    assert "failed before running any node" in report(tmp_path / "missing.json")
