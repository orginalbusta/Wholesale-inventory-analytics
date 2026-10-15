"""scripts/carry_over_deploy.py keeps one previous generation of hashed site files."""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from carry_over_deploy import FILE_LIST, carry_over, own_files  # noqa: E402

BASE = "https://example.test/site"


def make_site(root: Path, files: dict[str, str]) -> Path:
    for path, content in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content, encoding="utf-8")
    return root


def fake_live_site(files: dict[str, str]):
    """A fetch function serving `files` (plus their file list) from BASE."""
    served = {**files, FILE_LIST: "\n".join(sorted(files)) + "\n"}

    def fetch(url: str) -> bytes:
        path = url.removeprefix(BASE + "/")
        if path not in served:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return served[path].encode("utf-8")

    return fetch


def test_carries_previous_hashed_files_only(tmp_path):
    site = make_site(
        tmp_path,
        {
            "index.html": "new",
            "data/manifest.json": "new manifest",
            "data/marts/t/NEWHASH/t.parquet": "new data",
            "_app/immutable/chunk.NEW.js": "new js",
        },
    )
    live = fake_live_site(
        {
            "index.html": "old",
            "old-page/index.html": "old page",
            "data/manifest.json": "old manifest",
            "data/marts/t/OLDHASH/t.parquet": "old data",
            "_app/immutable/chunk.OLD.js": "old js",
        }
    )
    carried, _ = carry_over(site, BASE, fetch=live)

    assert carried == 2
    assert (site / "data/marts/t/OLDHASH/t.parquet").read_text() == "old data"
    assert (site / "_app/immutable/chunk.OLD.js").read_text() == "old js"
    # The new build's own files win; non-hashed old files are not resurrected.
    assert (site / "data/manifest.json").read_text() == "new manifest"
    assert (site / "index.html").read_text() == "new"
    assert not (site / "old-page").exists()
    # Carried files aren't listed as this deploy's own, so the next deploy drops them.
    listed = (site / FILE_LIST).read_text().split()
    assert "data/marts/t/OLDHASH/t.parquet" not in listed
    assert "data/marts/t/NEWHASH/t.parquet" in listed


def test_first_deploy_without_a_previous_list(tmp_path):
    site = make_site(tmp_path, {"index.html": "new", "data/manifest.json": "m"})

    def unreachable(url: str) -> bytes:
        raise urllib.error.URLError("no network")

    assert carry_over(site, BASE, fetch=unreachable) == (0, 0)
    assert (site / FILE_LIST).read_text().split() == own_files(site)
