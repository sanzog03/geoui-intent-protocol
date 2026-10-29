"""Parity tests for the in-process pydantic-ai toolsets (``worldview.tools.pai``).

The two GeoUI tools must expose the same names and descriptions as the MCP
server (golden ``akd_contract.json``), and protocol errors must surface as
``ModelRetry`` so the model can fix its intent instead of the turn aborting.
"""

import json
from pathlib import Path

import pytest
from pydantic_ai import ModelRetry

from geoui.core import GeoIntent, LayerRef, TimeWindow, Viewport
from worldview.tools import GET_STATE_DOC, RENDER_INTENT_DOC
from worldview.tools.pai import geoui_toolset, permalink_toolset

pytestmark = pytest.mark.agents

GOLDEN = json.loads((Path(__file__).parents[1] / "mcp" / "fixtures" / "akd_contract.json").read_text())


def test_tool_names_match_mcp_names():
    assert list(geoui_toolset.tools) == [
        "geo_ui_render_intent_tool",
        "geo_ui_get_state_tool",
        "geo_ui_list_intent_extensions_tool",
    ]
    assert list(permalink_toolset.tools) == ["worldview_permalink_tool"]


def test_descriptions_are_the_shared_docs_and_lead_the_golden_contract():
    render = geoui_toolset.tools["geo_ui_render_intent_tool"]
    state = geoui_toolset.tools["geo_ui_get_state_tool"]
    assert render.description == RENDER_INTENT_DOC
    assert state.description == GET_STATE_DOC
    # the MCP contract description is the doc plus akd's field-description suffix
    assert GOLDEN["geo_ui_render_intent_tool"]["akd_description"].startswith(RENDER_INTENT_DOC)
    assert GOLDEN["geo_ui_get_state_tool"]["akd_description"].startswith(GET_STATE_DOC)


def test_parameter_schemas_carry_names_and_field_descriptions():
    render = geoui_toolset.tools["geo_ui_render_intent_tool"].function_schema.json_schema
    assert list(render["properties"]) == ["intent", "embed_mode"]
    assert render["required"] == ["intent"]
    assert "GeoIntent" in json.dumps(render)  # the full intent model is in the schema
    assert render["properties"]["embed_mode"]["description"].startswith("If True, opens Worldview in embed mode")

    state = geoui_toolset.tools["geo_ui_get_state_tool"].function_schema.json_schema
    assert list(state["properties"]) == ["url"]

    permalink = permalink_toolset.tools["worldview_permalink_tool"].function_schema.json_schema
    # a single BaseModel parameter is flattened into the tool's own schema
    assert "layers" in permalink["properties"] and "projection" in permalink["properties"]


async def test_round_trip_through_the_toolset():
    intent = GeoIntent(
        viewport=Viewport(bbox=[-125, 32, -114, 42]),
        time=TimeWindow(instant="2025-09-15"),
        layers=[LayerRef(id="MODIS_Aqua_Aerosol", opacity=0.8)],
    )
    rendered = await geoui_toolset.tools["geo_ui_render_intent_tool"].function(intent)
    assert set(rendered) == {"url"}  # no akd "_response" key
    parsed = await geoui_toolset.tools["geo_ui_get_state_tool"].function(rendered["url"])
    assert parsed["intent"]["time"]["instant"] == "2025-09-15"
    assert any(layer["id"] == "MODIS_Aqua_Aerosol" for layer in parsed["intent"]["layers"])


async def test_undeclared_extension_fields_render_because_the_tool_pre_declares():
    """``compare:*`` fields without the extension URI was the top logged agent
    error in the poster runs and a retry in every compare/chart gold conversation;
    the tool now declares the supported extensions itself."""
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
    out = await geoui_toolset.tools["geo_ui_render_intent_tool"].function(undeclared)
    assert "t1=2025-09-14" in out["url"] and "cm=swipe" in out["url"]


async def test_protocol_errors_are_retryable_by_the_model():
    """An unsupported extension and an incomplete one come back as retry prompts."""
    unsupported = GeoIntent.model_validate({"layers": [{"id": "A"}], "elevation:exaggeration": 2})
    with pytest.raises(ModelRetry, match="not available in this deployment"):
        await geoui_toolset.tools["geo_ui_render_intent_tool"].function(unsupported)
    incomplete = GeoIntent.model_validate({"layers": [{"id": "A"}], "compare:mode": "spy"})
    with pytest.raises(ModelRetry, match="layers"):
        await geoui_toolset.tools["geo_ui_render_intent_tool"].function(incomplete)


async def test_list_intent_extensions_matches_the_adapter():
    from worldview.adapter import SUPPORTED_EXTENSIONS

    out = await geoui_toolset.tools["geo_ui_list_intent_extensions_tool"].function()
    assert [e["name"] for e in out["extensions"]] == [s.prefix for s in SUPPORTED_EXTENSIONS]
    compare = out["extensions"][0]
    assert compare["required"] == ["compare:layers"] and compare["scope"] == "intent"
    assert "properties" in compare["fields_schema"]


async def test_bad_url_is_retryable_by_the_model():
    with pytest.raises(ModelRetry):
        await geoui_toolset.tools["geo_ui_get_state_tool"].function("https://worldview.earthdata.nasa.gov/?p=mars&l=X")


async def test_permalink_tool_builds_a_url():
    from worldview.adapter import LayerSpec, WorldviewPermalinkInputSchema

    params = WorldviewPermalinkInputSchema(layers=[LayerSpec(id="MODIS_Aqua_Aerosol")], time="2025-09-15")
    out = await permalink_toolset.tools["worldview_permalink_tool"].function(params)
    assert out["url"].startswith("https://worldview.earthdata.nasa.gov/") and "t=2025-09-15" in out["url"]
    # argument validation itself is pydantic-ai's job: an invalid params payload
    # never reaches the function, the model gets the ValidationError as a retry.
