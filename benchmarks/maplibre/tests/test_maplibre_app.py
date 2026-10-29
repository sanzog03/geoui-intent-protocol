"""The MapLibre binding: the state comes from the page as a handle, and observe reads it back offline."""

import asyncio
from pathlib import Path

import pytest

from geoui import GeoIntent
from geouibench import BenchmarkApp, load_app_dir
from geouibench.app import snapshot_app
from geouibench.state import ExpectedState, compare_state
from maplibre.tests._fake_session import FakeSession

APP_DIR = load_app_dir(Path(__file__).resolve().parent.parent)
MaplibreApp = type(APP_DIR.app)
AOD = "MODIS_Aqua_Aerosol_Optical_Depth_3km"


def test_satisfies_the_protocol_with_one_agent_kind():
    assert isinstance(APP_DIR.app, BenchmarkApp)
    assert APP_DIR.app.agent_kinds == ("geoui",) and APP_DIR.app.name == "maplibre"
    assert APP_DIR.app.auto_layers == frozenset() and APP_DIR.app.discovery_tools == frozenset()
    assert APP_DIR.app.output_url(object()) is None
    assert APP_DIR.app.chatbot_role("geoui").startswith("A map assistant")
    with pytest.raises(ValueError, match="unknown agent kind"):
        APP_DIR.app.build_agent("vlm", cdp_endpoint=None, extra_capabilities=[])


def test_snapshot_reads_the_page_and_observe_round_trips_it():
    page = FakeSession()
    page.state["layers"] = [
        {"id": AOD, "visible": True, "opacity": 0.8},
        {"id": "Coastlines_15m", "visible": False, "opacity": None},
    ]
    page.state["time"] = {"instant": "2025-09-15"}
    page.state["compare:layers"] = [{"id": AOD}]
    page.state["compare:time"] = {"instant": "2025-09-14"}
    page.state["compare:mode"] = "swipe"
    app = MaplibreApp()
    app.session_factory = page.factory()

    handle = asyncio.run(snapshot_app(app, "http://cdp:9222"))
    assert handle.startswith("geoui+json:") and "/Users/" not in handle
    observed = app.observe(handle)
    assert [layer.id for layer in observed.layers] == [AOD]  # hidden layer dropped
    expected = ExpectedState.model_validate(
        {"layers": {AOD: 0.8}, "time": "2025-09-15", "compare": {"mode": "swipe", "time": "2025-09-14"}}
    )
    assert compare_state(observed, expected, auto_layers=app.auto_layers).score == 1.0


def test_observe_rejects_anything_else():
    with pytest.raises(ValueError, match="geoui\\+json"):
        MaplibreApp().observe("https://worldview.earthdata.nasa.gov/?l=a")
    with pytest.raises(ValueError):
        MaplibreApp().observe("geoui+json:not json")


def test_snapshot_is_none_when_the_page_is_unreachable(monkeypatch):
    monkeypatch.setenv("GEOUI_APP_URL", "http://127.0.0.1:1")
    app = MaplibreApp()
    assert asyncio.run(app.snapshot("http://127.0.0.1:1")) is None


def test_observe_keeps_namespaced_fields():
    handle = "geoui+json:" + GeoIntent.model_validate(
        {
            "layers": [{"id": AOD, "raster-styling:min": 0, "raster-styling:max": 2, "raster-styling:squash": True}],
            "time": {"instant": "2025-09-15"},
        }
    ).model_dump_json(by_alias=True)
    observed = MaplibreApp().observe(handle)
    assert observed.layers[0].extension_fields("raster-styling") == {
        "raster-styling:min": 0,
        "raster-styling:max": 2,
        "raster-styling:squash": True,
    }
