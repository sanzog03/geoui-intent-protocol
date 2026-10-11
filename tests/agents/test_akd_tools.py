"""Parity tests for the akd ``BaseTool`` wrappers used by the IESO agents.

Requires the ``agents`` extra (akd-ext installed); skipped otherwise.
"""

import inspect
import json
from pathlib import Path

import pytest

pytest.importorskip("akd")

from geoui.agents._akd_tools import (
    GeoUIGetStateInputSchema,
    GeoUIGetStateTool,
    GeoUIRenderIntentInputSchema,
    GeoUIRenderIntentTool,
)
from geoui.core import GeoIntent, LayerRef, TimeWindow, Viewport
from geoui.mcp._describe import describe
from geoui.tools import (
    GET_STATE_DOC,
    RENDER_INTENT_DOC,
    GeoUIGetStateRequest,
    GeoUIGetStateResult,
    GeoUIRenderIntentRequest,
    GeoUIRenderIntentResult,
)

pytestmark = pytest.mark.agents

GOLDEN = json.loads((Path(__file__).parents[1] / "mcp" / "fixtures" / "akd_contract.json").read_text())


def test_tool_names_match_mcp_names():
    assert GeoUIRenderIntentTool().name == "geo_ui_render_intent_tool"
    assert GeoUIGetStateTool().name == "geo_ui_get_state_tool"


def test_as_function_parameter_names():
    assert list(inspect.signature(GeoUIRenderIntentTool().as_function()).parameters) == ["intent", "embed_mode"]
    assert list(inspect.signature(GeoUIGetStateTool().as_function()).parameters) == ["url"]


def test_descriptions_match_mcp_server_and_golden():
    render, state = GeoUIRenderIntentTool(), GeoUIGetStateTool()
    assert render.description == describe(RENDER_INTENT_DOC, GeoUIRenderIntentRequest, GeoUIRenderIntentResult)
    assert state.description == describe(GET_STATE_DOC, GeoUIGetStateRequest, GeoUIGetStateResult)
    assert render.description == GOLDEN["geo_ui_render_intent_tool"]["akd_description"]
    assert state.description == GOLDEN["geo_ui_get_state_tool"]["akd_description"]


async def test_round_trip_through_akd_tools():
    intent = GeoIntent(
        viewport=Viewport(bbox=[-125, 32, -114, 42]),
        time=TimeWindow(instant="2025-09-15"),
        layers=[LayerRef(id="MODIS_Aqua_Aerosol", opacity=0.8)],
    )
    rendered = await GeoUIRenderIntentTool().arun(GeoUIRenderIntentInputSchema(intent=intent))
    parsed = await GeoUIGetStateTool().arun(GeoUIGetStateInputSchema(url=rendered.url))
    assert str(parsed.intent.time.instant) == "2025-09-15"
