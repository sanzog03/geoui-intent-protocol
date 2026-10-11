"""The frozen poster logs are published data: no machine-specific paths."""

from pathlib import Path

import pytest

RESULTS = Path(__file__).resolve().parents[1] / "benchmarks" / "results" / "poster-2026-05"


@pytest.mark.parametrize("name", ["runs.jsonl", "errors.jsonl"])
def test_frozen_logs_contain_no_absolute_user_paths(name):
    text = (RESULTS / name).read_text()
    assert "/Users/" not in text and "/home/" not in text
