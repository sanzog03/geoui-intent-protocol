"""App directories: how an application plugs into the utility without becoming a package.

An app directory looks like::

    benchmarks/<app>/
    ├── app.py               module-level ``APP``: an object satisfying BenchmarkApp
    │                        (optionally ``SYNTHETIC_STYLE`` for geouibench synthetic)
    ├── datasets/<name>.json conversational goldens (see geouibench.datasets)
    └── results/<run-id>/    one folder per run, written by geouibench run

``app.py`` is loaded by file path under a private module name, so the
directory needs no ``__init__.py`` and can carry any name, including one
that an installed package already uses.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from geouibench.app import BenchmarkApp

APP_FILE = "app.py"
APP_ATTR = "APP"
STYLE_ATTR = "SYNTHETIC_STYLE"
DATASETS_DIR = "datasets"
RESULTS_DIR = "results"


class AppDirError(ValueError):
    """The directory is not a usable app directory; the message says what is missing."""


class AppDir:
    """A loaded app directory."""

    def __init__(self, path: Path, module: ModuleType, app: BenchmarkApp) -> None:
        self.path = Path(path)
        self.module = module
        self.app = app

    @property
    def datasets_dir(self) -> Path:
        return self.path / DATASETS_DIR

    @property
    def results_dir(self) -> Path:
        return self.path / RESULTS_DIR

    def run_dir(self, run_id: str) -> Path:
        return self.results_dir / run_id

    def datasets(self) -> dict[str, Path]:
        """Every dataset in the directory, keyed by file stem."""
        if not self.datasets_dir.is_dir():
            return {}
        return {p.stem: p for p in sorted(self.datasets_dir.glob("*.json"))}

    def dataset(self, name: str) -> Path:
        """``datasets/<name>.json``, or the one file whose stem starts with ``<name>`` (``gold`` → ``gold_dataset.json``)."""
        exact = self.datasets_dir / f"{name}.json"
        if exact.is_file():
            return exact
        candidates = [p for stem, p in self.datasets().items() if stem.startswith(name)]
        if len(candidates) == 1:
            return candidates[0]
        have = ", ".join(self.datasets()) or "none"
        if not candidates:
            raise AppDirError(f"{self.path}: no dataset named {name!r} (have: {have})")
        raise AppDirError(f"{self.path}: dataset name {name!r} is ambiguous (have: {have})")

    def select_datasets(self, names: list[str] | str) -> dict[str, Path]:
        """``"all"`` or a list of names → ``{name: path}``; names keep their requested spelling."""
        if names == "all" or names == ["all"]:
            return self.datasets()
        return {name: self.dataset(name) for name in ([names] if isinstance(names, str) else names)}

    @property
    def synthetic_style(self) -> Any | None:
        return getattr(self.module, STYLE_ATTR, None)

    @property
    def relpath(self) -> str:
        """The directory relative to the current working directory when possible (what run.json records)."""
        try:
            return str(self.path.resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            return str(self.path.resolve())


def _module_name(path: Path) -> str:
    """Private, path-unique module name: two app directories may share a basename."""
    resolved = path.resolve()
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:8]
    return "geouibench_app_" + re.sub(r"\W", "_", resolved.name) + "_" + digest


def load_app_dir(path: Path | str) -> AppDir:
    """Load ``<path>/app.py`` and return its ``APP`` with the directory around it."""
    path = Path(path)
    app_file = path / APP_FILE
    if not app_file.is_file():
        raise AppDirError(f"{path}: no {APP_FILE} (an app directory holds app.py, datasets/, results/)")
    name = _module_name(path)
    module = sys.modules.get(name)
    if module is None or getattr(module, "__file__", None) != str(app_file):
        spec = importlib.util.spec_from_file_location(name, app_file)
        if spec is None or spec.loader is None:  # pragma: no cover
            raise AppDirError(f"{app_file}: cannot import")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
    app = getattr(module, APP_ATTR, None)
    if app is None:
        raise AppDirError(f"{app_file}: define a module-level {APP_ATTR} (an instance of your BenchmarkApp)")
    if not isinstance(app, BenchmarkApp):
        raise AppDirError(f"{app_file}: {APP_ATTR} does not satisfy geouibench.BenchmarkApp")
    if not app.agent_kinds:
        raise AppDirError(f"{app_file}: {APP_ATTR}.agent_kinds is empty")
    return AppDir(path, module, app)


__all__ = [
    "APP_ATTR",
    "APP_FILE",
    "DATASETS_DIR",
    "RESULTS_DIR",
    "STYLE_ATTR",
    "AppDir",
    "AppDirError",
    "load_app_dir",
]
