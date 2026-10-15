"""Smoke-check a running Dagster stack (used by CI after `docker compose up --wait`).

Passes when the webserver answers, the craftstones_dagster code location loaded without errors,
and the daemon's scheduler and run queue report healthy. Standard library only, so it runs
on the CI runner without installing the project.

    python scripts/check_dagster_stack.py [--url http://localhost:3000]
"""

import argparse
import json
import sys
import time
import urllib.request

QUERY = """
{
  workspaceOrError {
    ... on Workspace {
      locationEntries {
        name
        locationOrLoadError {
          __typename
          ... on PythonError { message }
          ... on RepositoryLocation { repositories { jobs { name } schedules { name } } }
        }
      }
    }
  }
  instance { daemonHealth { allDaemonStatuses { daemonType healthy required } } }
}
"""
REQUIRED_DAEMONS = {"SCHEDULER", "QUEUED_RUN_COORDINATOR"}


def graphql(url: str, query: str) -> dict:
    request = urllib.request.Request(
        f"{url}/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["data"]


def check(url: str) -> list[str]:
    """Return a list of problems (empty when everything is healthy)."""
    data = graphql(url, QUERY)
    problems = []

    entries = {
        e["name"]: e["locationOrLoadError"] for e in data["workspaceOrError"]["locationEntries"]
    }
    location = entries.get("craftstones_dagster") or next(iter(entries.values()), None)
    if location is None or location["__typename"] != "RepositoryLocation":
        problems.append(f"code location did not load: {location}")
    else:
        jobs = {j["name"] for r in location["repositories"] for j in r["jobs"]}
        if "daily_pipeline_job" not in jobs:
            problems.append(f"daily_pipeline_job missing; jobs = {sorted(jobs)}")

    statuses = data["instance"]["daemonHealth"]["allDaemonStatuses"]
    healthy = {s["daemonType"] for s in statuses if s["healthy"]}
    missing = REQUIRED_DAEMONS - healthy
    if missing:
        problems.append(f"daemons not healthy: {sorted(missing)}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:3000")
    parser.add_argument("--timeout", type=int, default=120, help="seconds to wait for daemons")
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    while True:
        try:
            problems = check(args.url)
        except OSError as exc:
            problems = [f"webserver not reachable: {exc}"]
        if not problems:
            print("Dagster stack healthy: code location loaded, scheduler and run queue running.")
            return
        if time.monotonic() > deadline:
            print("\n".join(problems), file=sys.stderr)
            sys.exit(1)
        time.sleep(5)  # daemons report a heartbeat every few seconds after startup


if __name__ == "__main__":
    main()
