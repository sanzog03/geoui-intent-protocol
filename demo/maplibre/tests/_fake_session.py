"""An in-memory stand-in for a ``window.geoui`` page: the SDK's contract without a browser."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

SCHEMAS = Path(__file__).resolve().parents[3] / "schemas" / "extensions"
DEFAULT_LAYERS = [
    {"id": "A", "title": "Layer A", "time": {"start": "2000-01-01", "end": None, "period": "P1D"}},
    {"id": "B", "title": "Layer B"},
]


def spec_json(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / f"{name}.json").read_text())


class FakeSession:
    """Replace-semantics state, the catalogue from the committed schema JSON, and a log of calls."""

    def __init__(self, extensions=("compare", "raster_styling"), layers=DEFAULT_LAYERS, *, refuse: dict | None = None):
        self.catalogue = {
            "version": "0.1.0-fake",
            "protocol": "1.0.0",
            "extensions": [spec_json(n) for n in extensions],
            "layers": list(layers),
        }
        self.state: dict[str, Any] = {
            "geoui_version": "1.0.0",
            "geoui_extensions": [e["uri"] for e in self.catalogue["extensions"]],
            "viewport": {"bbox": None, "crs": "EPSG:4326"},
            "time": None,
            "layers": [],
        }
        self.refuse = refuse  # a RenderResult {ok: False, ...} the page would answer with
        self.calls: list[tuple[str, Any]] = []
        self.opened = 0

    async def describe(self) -> dict[str, Any]:
        self.calls.append(("describe", None))
        return json.loads(json.dumps(self.catalogue))

    async def get_state(self) -> dict[str, Any]:
        self.calls.append(("get_state", None))
        return json.loads(json.dumps(self.state))

    async def render(self, intent: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("render", intent))
        if self.refuse is not None:
            raise ValueError(str(self.refuse.get("error")))
        self.state = {
            "geoui_version": "1.0.0",
            "geoui_extensions": [e["uri"] for e in self.catalogue["extensions"]],
            "viewport": intent.get("viewport") or {"bbox": None, "crs": "EPSG:4326"},
            "time": intent.get("time"),
            "layers": [{"visible": True, "opacity": None, **layer} for layer in intent.get("layers", [])],
            **{k: v for k, v in intent.items() if ":" in k},
        }
        return {"ok": True, "state": json.loads(json.dumps(self.state)), "settled": True}

    def factory(self):
        @asynccontextmanager
        async def _open() -> AsyncIterator[FakeSession]:
            self.opened += 1
            yield self

        return _open
