"""Keep the previous deploy's hashed files in the new GitHub Pages site, for one deploy.

Why: GitHub Pages serves every file with a ~10 minute browser cache. The dashboard's
`data/manifest.json` names parquet files by content hash (`data/marts/<table>/<hash>/...`), and
pages load JavaScript chunks by hash (`_app/immutable/...`). Each deploy replaces those hashed
files, so a visitor whose browser still holds the old manifest or old HTML asks for files that
no longer exist and sees query errors until the cache expires.

Fix: every deploy writes `deploy-files.txt` listing the files it built itself. The next deploy
reads that list from the live site and downloads any hashed file (under `_app/immutable/` or
`data/`) that it no longer builds. Only the previous deploy's own files are carried, so files
never pile up beyond one extra generation. Failing to reach the live site never fails the deploy.

    python scripts/carry_over_deploy.py site https://orginalbusta.github.io/Wholesale-inventory-analytics
"""

import argparse
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

FILE_LIST = "deploy-files.txt"
CARRIED_PREFIXES = ("_app/immutable/", "data/")

Fetch = Callable[[str], bytes]


def http_fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def own_files(site: Path) -> list[str]:
    """Every file this build produced, as site-relative POSIX paths."""
    return sorted(
        p.relative_to(site).as_posix()
        for p in site.rglob("*")
        if p.is_file() and p.name != FILE_LIST
    )


def write_file_list(site: Path) -> list[str]:
    files = own_files(site)
    (site / FILE_LIST).write_text("\n".join(files) + "\n", encoding="utf-8")
    return files


def carry_over(site: Path, base_url: str, fetch: Fetch = http_fetch) -> tuple[int, int]:
    """Download the previous deploy's hashed files that this build doesn't have.

    Returns (files carried, bytes carried). Writes this build's own file list first, so carried
    files are never listed and are dropped again by the following deploy.
    """
    current = set(write_file_list(site))
    try:
        previous = fetch(f"{base_url}/{FILE_LIST}").decode("utf-8").split()
    except (urllib.error.URLError, OSError) as exc:
        print(f"No previous file list ({exc}); nothing to carry over.")
        return 0, 0

    to_carry = [p for p in previous if p.startswith(CARRIED_PREFIXES) and p not in current]
    carried = carried_bytes = 0
    for path in to_carry:
        try:
            content = fetch(f"{base_url}/{path}")
        except (urllib.error.URLError, OSError) as exc:
            print(f"  skipped {path}: {exc}")
            continue
        target = site / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        carried += 1
        carried_bytes += len(content)
    return carried, carried_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("site", type=Path, help="assembled site folder about to be deployed")
    parser.add_argument("base_url", help="public URL of the currently deployed site")
    args = parser.parse_args()
    if not args.site.is_dir():
        sys.exit(f"{args.site} is not a directory")
    carried, size = carry_over(args.site, args.base_url.rstrip("/"))
    print(f"Carried over {carried} file(s) ({size / 1e6:.1f} MB) from the previous deploy.")


if __name__ == "__main__":
    main()
