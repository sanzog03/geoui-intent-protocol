"""The state judge: what the UI shows versus what the scenario expects.

The vocabulary is GeoIntent (layers with opacity, time, projection, and the
compare / chart / raster-styling extension fields), used only because it is
the schema this repo already has for "what is on screen". The judge does
not know how the state was reached: an application's ``observe`` turns the
URL an agent left behind, whether it got there by rendering an intent or
by clicking through the UI, into the same :data:`UIState`, and the same
comparison runs. Viewport bounds (``viewport.bbox``, ``chart:area``) are
never judged; they vary too much across plausibly-correct framings.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any, Protocol

from dateutil import parser as dateparser
from pydantic import BaseModel, ConfigDict, Field

from geoui import LayerRef
from geoui.extensions import chart, compare, raster_styling
from geouibench.app import UIState


class CompareExpectation(BaseModel):
    """Expected ``compare`` extension state. Only the fields given are judged."""

    model_config = ConfigDict(extra="forbid")

    time: date | None = None
    mode: str | None = None
    layers: list[str] | None = Field(default=None, description="Layer ids that must be on side B")


class ChartExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str | None = None
    start: date | None = None
    end: date | None = None
    autoload: bool | None = None


class StylingExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str
    min: float | None = None
    max: float | None = None
    squash: bool | None = None


class ExpectedState(BaseModel):
    """What a scenario expects the UI to show. Every field is optional; only given fields are judged."""

    model_config = ConfigDict(extra="forbid")

    layers: dict[str, float | None] = Field(
        default_factory=dict,
        description="Layer ids that must be visible, mapped to the expected opacity (None = any)",
    )
    time: date | None = None
    crs: str | None = None
    compare: CompareExpectation | None = None
    chart: ChartExpectation | None = None
    styling: StylingExpectation | None = None


class StateMatch(BaseModel):
    """Outcome of one comparison: which checks matched, which missed, and the fraction."""

    matched: list[str] = Field(default_factory=list)
    missed: list[str] = Field(default_factory=list)
    score: float
    error: str | None = None


def _as_utc_date(value: Any) -> date | None:
    """Coerce an ISO date/time, or an app spelling such as ``2025-09-15-T03:06:50Z``, to a UTC date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        return value
    else:
        text = str(value)
        # some apps write ``YYYY-MM-DD-THH:MM:SSZ``; dateutil needs the dash before ``T`` gone.
        if len(text) > 11 and text[10:12] == "-T":
            text = text[:10] + "T" + text[12:]
        dt = dateparser.parse(text)
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.date()


def _opacity_equal(observed: float | None, expected: float | None) -> bool:
    if expected is None:
        return True
    return abs((observed if observed is not None else 1.0) - expected) < 1e-6


def _visible_layers(layers: Iterable[LayerRef]) -> dict[str, LayerRef]:
    return {layer.id: layer for layer in layers if layer.visible}


class _Checks:
    def __init__(self) -> None:
        self.matched: list[str] = []
        self.missed: list[str] = []

    def add(self, name: str, ok: bool) -> None:
        (self.matched if ok else self.missed).append(name)

    def result(self, error: str | None = None) -> StateMatch:
        total = len(self.matched) + len(self.missed)
        score = 1.0 if total == 0 else len(self.matched) / total
        return StateMatch(matched=self.matched, missed=self.missed, score=score, error=error)


def _expected_check_names(expected: ExpectedState) -> list[str]:
    """Every check ``compare_state`` would run, so a failed observation can list them all as missed."""
    names = [f"layer:{layer_id}" for layer_id in expected.layers]
    if expected.time is not None:
        names.append("time")
    if expected.crs is not None:
        names.append("crs")
    if expected.compare is not None:
        names.append("compare")
        if expected.compare.time is not None:
            names.append("compare.time")
        if expected.compare.mode is not None:
            names.append("compare.mode")
        for layer_id in expected.compare.layers or []:
            names.append(f"compare.layer:{layer_id}")
    if expected.chart is not None:
        names.append("chart")
        for field in ("layer", "start", "end", "autoload"):
            if getattr(expected.chart, field) is not None:
                names.append(f"chart.{field}")
    if expected.styling is not None:
        names.append("styling")
        for field in ("min", "max", "squash"):
            if getattr(expected.styling, field) is not None:
                names.append(f"styling.{field}")
    return names


def compare_state(observed: UIState, expected: ExpectedState, *, auto_layers: frozenset[str]) -> StateMatch:
    """Judge ``observed`` against ``expected``.

    ``auto_layers`` are layers the application injects on its own; their
    presence is never required and never penalised unless ``expected.layers``
    names them. Hidden layers are not "present". Opacity ``None`` means 1.0.
    """
    checks = _Checks()
    visible = _visible_layers(observed.layers)

    for layer_id, opacity in expected.layers.items():
        layer = visible.get(layer_id)
        checks.add(f"layer:{layer_id}", layer is not None and _opacity_equal(layer.opacity, opacity))

    if expected.time is not None:
        observed_date = _as_utc_date(observed.time.instant) if observed.time is not None else None
        checks.add("time", observed_date == expected.time)

    if expected.crs is not None:
        checks.add("crs", observed.viewport.crs == expected.crs)

    if expected.compare is not None:
        fields = _safe_extract(compare.extract, observed)
        checks.add("compare", fields is not None)
        if expected.compare.time is not None:
            observed_date = _as_utc_date(fields.time.instant) if fields is not None and fields.time else None
            checks.add("compare.time", observed_date == expected.compare.time)
        if expected.compare.mode is not None:
            checks.add("compare.mode", fields is not None and fields.mode == expected.compare.mode)
        side_b = _visible_layers(fields.layers) if fields is not None else {}
        for layer_id in expected.compare.layers or []:
            checks.add(f"compare.layer:{layer_id}", layer_id in side_b)

    if expected.chart is not None:
        fields = _safe_extract(chart.extract, observed)
        checks.add("chart", fields is not None)
        if expected.chart.layer is not None:
            checks.add("chart.layer", fields is not None and fields.layer == expected.chart.layer)
        if expected.chart.start is not None:
            start = _as_utc_date(fields.time.start) if fields is not None and fields.time else None
            checks.add("chart.start", start == expected.chart.start)
        if expected.chart.end is not None:
            end = _as_utc_date(fields.time.end) if fields is not None and fields.time else None
            checks.add("chart.end", end == expected.chart.end)
        if expected.chart.autoload is not None:
            checks.add("chart.autoload", fields is not None and fields.autoload == expected.chart.autoload)

    if expected.styling is not None:
        target = visible.get(expected.styling.layer)
        styling = raster_styling.extract(target) if target is not None else None
        checks.add("styling", styling is not None)
        if expected.styling.min is not None:
            checks.add("styling.min", styling is not None and styling.min == expected.styling.min)
        if expected.styling.max is not None:
            checks.add("styling.max", styling is not None and styling.max == expected.styling.max)
        if expected.styling.squash is not None:
            checks.add("styling.squash", styling is not None and bool(styling.squash) == expected.styling.squash)

    del auto_layers  # presence of auto layers is neither required nor penalised; kept in the signature for intent
    return checks.result()


def _safe_extract(extract: Any, observed: UIState) -> Any:
    try:
        return extract(observed)
    except ValueError:
        return None


def checkpoint_reached(observed: UIState, checkpoint: ExpectedState, *, auto_layers: frozenset[str]) -> bool:
    """A checkpoint is reached only when every one of its checks matches."""
    return compare_state(observed, checkpoint, auto_layers=auto_layers).score == 1.0


class _Observer(Protocol):
    auto_layers: frozenset[str]

    def observe(self, url: str) -> UIState: ...


def judge_url(app: _Observer, url: str | None, expected: ExpectedState) -> StateMatch:
    """Observe ``url`` through the application and judge it; failures score 0 with every check missed."""
    if not url:
        return StateMatch(matched=[], missed=_expected_check_names(expected), score=0.0, error="no URL")
    try:
        observed = app.observe(url)
    except Exception as exc:  # noqa: BLE001 — any parse failure is "the agent left no judgeable state"
        return StateMatch(
            matched=[], missed=_expected_check_names(expected), score=0.0, error=f"{type(exc).__name__}: {exc}"
        )
    return compare_state(observed, expected, auto_layers=app.auto_layers)


__all__ = [
    "ChartExpectation",
    "CompareExpectation",
    "ExpectedState",
    "StateMatch",
    "StylingExpectation",
    "UIState",
    "checkpoint_reached",
    "compare_state",
    "judge_url",
]
