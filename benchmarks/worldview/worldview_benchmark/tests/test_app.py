"""The Worldview binding reads the same UI state from either agent's URL."""

import os
from datetime import date

import pytest

from geobench import BenchmarkApp
from geobench.state import ExpectedState, compare_state, judge_url
from geoui import GeoIntent, LayerRef, TimeWindow
from worldview.adapter.mapping import intent_to_url
from worldview.adapter.permalink import BASE_LAYERS_SET, DEFAULT_REFERENCE_OVERLAYS
from worldview.agents import GeoUIAgentOutput, TextOutput, VLMAgentOutput
from worldview_benchmark.app import WorldviewApp

AOD = "MODIS_Aqua_Aerosol_Optical_Depth_3km"

# Read back from ``window.location.href`` by the VLM agent in the poster run
# (benchmarks/manual/results/poster-2026-05/runs.jsonl): hidden layers, ``lg``,
# ``s``, and a timestamp inside ``t``.
LIVE_VLM_URL = (
    "https://worldview.earthdata.nasa.gov/?l=Reference_Labels_15m(hidden),Reference_Features_15m(hidden),"
    "Coastlines_15m,MODIS_Aqua_Aerosol_Optical_Depth_3km,OCI_PACE_True_Color(hidden),"
    "VIIRS_NOAA21_CorrectedReflectance_TrueColor(hidden),VIIRS_NOAA20_CorrectedReflectance_TrueColor(hidden),"
    "VIIRS_SNPP_CorrectedReflectance_TrueColor(hidden),MODIS_Aqua_CorrectedReflectance_TrueColor(hidden),"
    "MODIS_Terra_CorrectedReflectance_TrueColor&lg=true&t=2025-09-15-T02%3A05%3A52Z"
)
LIVE_VLM_URL_DATE_CHANGE = (
    "https://worldview.earthdata.nasa.gov/?v=-88.95,24.37,-74.42,32.75&l=Reference_Labels_15m(hidden),"
    "Reference_Features_15m(hidden),Coastlines_15m,OCI_PACE_True_Color(hidden),"
    "VIIRS_NOAA21_CorrectedReflectance_TrueColor(hidden),VIIRS_NOAA20_CorrectedReflectance_TrueColor(hidden),"
    "VIIRS_SNPP_CorrectedReflectance_TrueColor,MODIS_Aqua_CorrectedReflectance_TrueColor(hidden),"
    "MODIS_Terra_CorrectedReflectance_TrueColor&lg=true&s=-81.6886,28.566&t=2024-09-27-T02%3A49%3A10Z"
)


@pytest.fixture
def app() -> WorldviewApp:
    return WorldviewApp()


def test_satisfies_the_protocol(app):
    assert isinstance(app, BenchmarkApp)
    assert app.name == "worldview"
    assert app.agent_kinds == ("geoui", "vlm")
    assert app.auto_layers == BASE_LAYERS_SET | frozenset(DEFAULT_REFERENCE_OVERLAYS)
    assert {"search_collections", "search_worldview_layers", "sde_search_tool"} <= app.discovery_tools


def test_observe_live_vlm_url_drops_hidden_layers_and_keeps_the_date(app):
    state = app.observe(LIVE_VLM_URL)
    assert [layer.id for layer in state.layers] == [
        "Coastlines_15m",
        AOD,
        "MODIS_Terra_CorrectedReflectance_TrueColor",
    ]
    assert all(layer.visible for layer in state.layers)
    expected = ExpectedState(layers={AOD: None}, time=date(2025, 9, 15))
    assert compare_state(state, expected, auto_layers=app.auto_layers).score == 1.0


def test_observe_live_vlm_url_with_a_base_layer_in_expected(app):
    expected = ExpectedState(layers={"VIIRS_SNPP_CorrectedReflectance_TrueColor": None}, time=date(2024, 9, 27))
    assert judge_url(app, LIVE_VLM_URL_DATE_CHANGE, expected).score == 1.0


def test_observe_geoui_permalink_enters_the_same_pipeline(app):
    intent = GeoIntent(time=TimeWindow(instant="2025-09-15"), layers=[LayerRef(id=AOD, opacity=1.0)])
    url = intent_to_url(intent)
    expected = ExpectedState(layers={AOD: 1.0}, time=date(2025, 9, 15))
    assert judge_url(app, url, expected).score == 1.0


def test_observe_rejects_garbage(app):
    with pytest.raises(ValueError):
        app.observe("not a url at all")


def test_output_url_reads_structured_outputs_only(app):
    assert app.output_url(GeoUIAgentOutput(result="r", url="https://x")) == "https://x"
    assert app.output_url(VLMAgentOutput(result="r", url="https://y")) == "https://y"
    assert app.output_url(TextOutput(content="hello")) is None
    assert app.output_url(None) is None


def test_chatbot_roles_are_one_sentence_each(app):
    for kind in app.agent_kinds:
        role = app.chatbot_role(kind)
        assert role.endswith(".") and "\n" not in role


@pytest.mark.agents
def test_build_agent_binds_each_kind(app, monkeypatch):
    from worldview.tests.agents._surface import DUMMY_ENV

    for key, value in DUMMY_ENV.items():
        monkeypatch.setenv(key, value)
    os.environ.setdefault("OPENAI_API_KEY", "dummy")
    geoui = app.build_agent("geoui", cdp_endpoint="http://localhost:9222", extra_capabilities=[])
    vlm = app.build_agent("vlm", cdp_endpoint="http://localhost:9222", extra_capabilities=[])
    assert geoui.name == "worldview_geoui_agent"
    assert vlm.name == "worldview_vlm_agent"
    with pytest.raises(ValueError):
        app.build_agent("nope", cdp_endpoint=None, extra_capabilities=[])
