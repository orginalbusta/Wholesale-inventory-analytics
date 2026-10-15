"""Turn a failed dbt run into a short, readable report (used by CI when `dbt build` fails).

Reads target/run_results.json and lists every model, test, seed or snapshot that errored or
failed, with dbt's message. In GitHub Actions the report is also written to the job summary
($GITHUB_STEP_SUMMARY), so a reviewer sees what broke without scrolling through the log.

    python scripts/dbt_failure_summary.py [transform/target/run_results.json]
"""

import json
import os
import sys
from pathlib import Path

DEFAULT_RESULTS = Path("transform/target/run_results.json")
FAILED = {"error", "fail", "runtime error"}


def failures(run_results: dict) -> list[dict]:
    return [r for r in run_results["results"] if r["status"] in FAILED]


def report(results_path: Path) -> str:
    if not results_path.exists():
        return (
            "### dbt failed before running any node\n\n"
            "No `run_results.json` was written, so the project didn't parse or compile "
            "(for example a `ref()` to a model that doesn't exist, or invalid YAML). "
            "The error is in the step log above.\n"
        )
    run_results = json.loads(results_path.read_text(encoding="utf-8"))
    failed = failures(run_results)
    if not failed:
        return "### dbt: no failed nodes\n"
    lines = [
        f"### dbt: {len(failed)} node(s) failed\n",
        "| Node | Status | Message |",
        "|---|---|---|",
    ]
    for r in failed:
        node = r["unique_id"].split(".", 2)[-1]  # model.craftstones.stg_x -> stg_x
        message = " ".join((r.get("message") or "").split())[:400].replace("|", "\\|")
        lines.append(f"| `{node}` | {r['status']} | {message} |")
    skipped = sum(r["status"] == "skipped" for r in run_results["results"])
    if skipped:
        lines.append(f"\n{skipped} downstream node(s) were skipped because of these failures.")
    return "\n".join(lines) + "\n"


def main() -> None:
    results_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RESULTS
    text = report(results_path)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
