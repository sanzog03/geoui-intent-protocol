"""An app directory is app.py + datasets/ + results/; the loader validates it and resolves datasets by name."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from geouibench.apps import AppDir, AppDirError, load_app_dir

FAKE_APP_SRC = """
from geouibench.tests._fake_app import FakeApp
APP = FakeApp()
"""


def make_app_dir(tmp_path: Path, *, datasets: dict[str, list] | None = None, src: str = FAKE_APP_SRC) -> Path:
    app_dir = tmp_path / "myapp"
    app_dir.mkdir(parents=True)
    (app_dir / "app.py").write_text(src)
    for name, goldens in (datasets or {}).items():
        (app_dir / "datasets").mkdir(exist_ok=True)
        (app_dir / "datasets" / f"{name}.json").write_text(json.dumps(goldens))
    return app_dir


def test_load_app_dir_returns_the_app_and_paths(tmp_path):
    app_dir = make_app_dir(tmp_path, datasets={"gold_dataset": [], "synthetic_queries": []})
    loaded = load_app_dir(app_dir)
    assert isinstance(loaded, AppDir)
    assert loaded.app.name == "fake" and loaded.app.agent_kinds == ("x", "y")
    assert loaded.datasets_dir == app_dir / "datasets" and loaded.results_dir == app_dir / "results"
    assert loaded.run_dir("r1") == app_dir / "results" / "r1"
    assert list(loaded.datasets()) == ["gold_dataset", "synthetic_queries"]
    assert loaded.synthetic_style is None


def test_dataset_names_resolve_exactly_or_by_unique_prefix(tmp_path):
    loaded = load_app_dir(make_app_dir(tmp_path, datasets={"gold_dataset": [], "synthetic_queries": [], "gold": []}))
    assert loaded.dataset("gold").name == "gold.json"  # exact wins
    assert loaded.dataset("synthetic").name == "synthetic_queries.json"  # unique prefix
    with pytest.raises(AppDirError, match="no dataset named 'nope'"):
        loaded.dataset("nope")
    (loaded.datasets_dir / "gold.json").unlink()
    assert loaded.dataset("g").name == "gold_dataset.json"
    (loaded.datasets_dir / "gamma.json").write_text("[]")
    with pytest.raises(AppDirError, match="ambiguous"):
        loaded.dataset("g")


def test_select_datasets_all_or_names(tmp_path):
    loaded = load_app_dir(make_app_dir(tmp_path, datasets={"gold_dataset": [], "synthetic_queries": []}))
    assert list(loaded.select_datasets("all")) == ["gold_dataset", "synthetic_queries"]
    assert list(loaded.select_datasets(["synthetic", "gold"])) == ["synthetic", "gold"]
    assert loaded.select_datasets("gold") == {"gold": loaded.datasets_dir / "gold_dataset.json"}


def test_loader_rejects_bad_directories(tmp_path):
    with pytest.raises(AppDirError, match="no app.py"):
        load_app_dir(tmp_path)
    with pytest.raises(AppDirError, match="define a module-level APP"):
        load_app_dir(make_app_dir(tmp_path / "a", src="x = 1\n"))
    with pytest.raises(AppDirError, match="does not satisfy"):
        load_app_dir(make_app_dir(tmp_path / "b", src="APP = object()\n"))
    with pytest.raises(ZeroDivisionError):
        load_app_dir(make_app_dir(tmp_path / "c", src="1/0\n"))
    assert not [
        m for m in sys.modules if m.startswith("geouibench_app_") and m.endswith("myapp") and sys.modules[m] is None
    ]


def test_two_app_directories_with_the_same_basename_do_not_collide(tmp_path):
    one = load_app_dir(make_app_dir(tmp_path / "one"))
    two = load_app_dir(make_app_dir(tmp_path / "two"))
    assert one.app is not two.app
    assert load_app_dir(tmp_path / "one" / "myapp").app is one.app  # same file → cached module
