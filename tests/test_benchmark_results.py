"""Committed benchmark artifacts are published data: no machine-specific paths."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "benchmarks" / "worldview_legacy" / "results" / "poster-2026-05"
RUNS = ROOT / "benchmarks" / "worldview" / "results"


def _artifacts() -> list[Path]:
    files = [MANUAL / "runs.jsonl", MANUAL / "errors.jsonl"]
    if RUNS.exists():
        files += [p for p in RUNS.rglob("*") if p.is_file() and p.suffix in (".jsonl", ".json", ".md")]
    return files


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: str(p.relative_to(ROOT)))
def test_committed_artifacts_contain_no_absolute_user_paths(path):
    text = path.read_text()
    assert "/Users/" not in text and "/home/" not in text
