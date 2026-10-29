"""Parity of the in-process toolset with the MCP server, and ModelRetry on refusals."""

import json
from pathlib import Path

import pytest
from pydantic_ai import ModelRetry

from geoui.core import GeoIntent
from geoui_bridge.tools import GET_STATE_DOC, LIST_INTENT_EXTENSIONS_DOC, RENDER_INTENT_DOC
from geoui_bridge.tools.pai import make_geoui_toolset

from ._fake_session import FakeSession

GOLDEN = json.loads((Path(__file__).parent / "mcp" / "fixtures" / "bridge_contract.json").read_text())
NAMES = ["geo_ui_render_intent_tool", "geo_ui_get_state_tool", "geo_ui_list_intent_extensions_tool"]


def test_tool_names_and_docs_match_the_mcp_contract():
    toolset = make_geoui_toolset(session_factory=FakeSession().factory())
    assert list(toolset.tools) == NAMES
    assert toolset.tools[NAMES[0]].description == RENDER_INTENT_DOC
    assert toolset.tools[NAMES[1]].description == GET_STATE_DOC
    assert toolset.tools[NAMES[2]].description == LIST_INTENT_EXTENSIONS_DOC
    for name, doc in zip(NAMES, (RENDER_INTENT_DOC, GET_STATE_DOC, LIST_INTENT_EXTENSIONS_DOC), strict=True):
        assert GOLDEN[name]["description"].startswith(doc)


def test_render_schema_has_only_the_intent():
    toolset = make_geoui_toolset(session_factory=FakeSession().factory())
    schema = toolset.tools[NAMES[0]].function_schema.json_schema
    assert list(schema["properties"]) == ["intent"] and schema["required"] == ["intent"]
    assert "GeoIntent" in json.dumps(schema)
    assert toolset.tools[NAMES[1]].function_schema.json_schema.get("properties", {}) == {}


async def test_round_trip_opens_a_session_per_call_and_retries_on_refusal():
    page = FakeSession()
    toolset = make_geoui_toolset(session_factory=page.factory())
    listed = await toolset.tools[NAMES[2]].function()
    assert [e["name"] for e in listed["extensions"]] == ["compare", "raster-styling"]
    rendered = await toolset.tools[NAMES[0]].function(intent=GeoIntent.model_validate({"layers": [{"id": "B"}]}))
    assert rendered["settled"] is True and rendered["intent"]["layers"][0]["id"] == "B"
    assert (await toolset.tools[NAMES[1]].function())["intent"]["layers"][0]["id"] == "B"
    assert page.opened == 3
    with pytest.raises(ModelRetry, match="unknown layer id"):
        await toolset.tools[NAMES[0]].function(intent=GeoIntent.model_validate({"layers": [{"id": "nope"}]}))
