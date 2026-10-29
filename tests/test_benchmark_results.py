"""Committed benchmark artifacts are published data: no machine-specific paths.

Only files git tracks are scanned: a run in progress (or one abandoned before
``geouibench summarize`` scrubbed it) is not published data, and deepeval's own
result JSON legitimately holds absolute paths until that scrub runs.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIRS = ("benchmarks/worldview_legacy/results", "benchmarks/worldview/results", "benchmarks/maplibre/results")
MARKERS = ("/Users/", "/home/")


def _tracked_artifacts() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--", *RESULT_DIRS], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):  # not a git checkout: scan everything that is there
        out = "\n".join(str(p.relative_to(ROOT)) for d in RESULT_DIRS for p in (ROOT / d).rglob("*") if p.is_file())
    return [ROOT / line for line in out.splitlines() if line.endswith((".jsonl", ".json", ".md"))]


@pytest.mark.parametrize("path", _tracked_artifacts(), ids=lambda p: str(p.relative_to(ROOT)))
def test_committed_artifacts_contain_no_absolute_user_paths(path):
    text = path.read_text()
    offenders = [marker for marker in MARKERS if marker in text]  # keep the assertion small: never repr the file
    assert not offenders, f"{path.relative_to(ROOT)} contains {offenders}"
