"""Parity tests for the akd ``BaseTool`` wrappers used by the IESO agents.

Requires the ``agents`` extra (akd-ext installed); skipped otherwise.
"""

import inspect
import json
from pathlib import Path

import pytest

pytest.importorskip("akd")

from geoui.core import GeoIntent, LayerRef, TimeWindow, Viewport
from worldview.mcp._describe import describe
from worldview.tools import (
    GET_STATE_DOC,
    RENDER_INTENT_DOC,
    GeoUIGetStateRequest,
    GeoUIGetStateResult,
    GeoUIRenderIntentRequest,
    GeoUIRenderIntentResult,
)
from worldview.tools.akd import (
    GeoUIGetStateInputSchema,
    GeoUIGetStateTool,
    GeoUIRenderIntentInputSchema,
    GeoUIRenderIntentTool,
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


async def test_protocol_errors_are_retryable_by_the_model():
    """A GeoIntent that uses ``compare:*`` without declaring the extension must
    reach the model as a retry prompt (akd-ext maps SchemaValidationError to
    pydantic_ai.ModelRetry), not escape and abort the whole turn. This was
    the top logged agent error in the poster runs."""
    from akd._base.errors import SchemaValidationError
    from akd_ext.agents._base.pydantic_ai._utils import akd_to_pai_tool
    from pydantic_ai import ModelRetry

    undeclared = GeoIntent.model_validate(
        {
            "viewport": {"bbox": [-125, 32, -114, 42]},
            "time": {"instant": "2025-09-15"},
            "layers": [{"id": "MODIS_Aqua_Aerosol_Optical_Depth_3km"}],
            "compare:layers": [{"id": "MODIS_Aqua_Aerosol_Optical_Depth_3km"}],
            "compare:time": {"instant": "2025-09-14"},
            "compare:mode": "swipe",
        }
    )
    with pytest.raises(SchemaValidationError, match="does not declare"):
        await GeoUIRenderIntentTool().arun(GeoUIRenderIntentInputSchema(intent=undeclared))

    pai_tool = akd_to_pai_tool(GeoUIRenderIntentTool())
    with pytest.raises(ModelRetry, match="geoui_extensions"):
        await pai_tool.function(intent=undeclared)


async def test_bad_url_is_retryable_by_the_model():
    from akd._base.errors import SchemaValidationError

    with pytest.raises(SchemaValidationError):
        await GeoUIGetStateTool().arun(GeoUIGetStateInputSchema(url="https://worldview.earthdata.nasa.gov/?p=mars&l=X"))
