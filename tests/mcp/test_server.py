"""Contract tests for the standalone GeoUI MCP server.

The golden fixture ``fixtures/akd_contract.json`` was captured from the
akd-ext implementation (the one deployed on FastMCP Cloud) with an in-process
``fastmcp.Client``. The standalone server must expose the same tool names,
input schemas and descriptions. The one intentional delta: the akd
``OutputSchema`` leaked an empty ``_response`` key, which is dropped here.
"""

import json
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from geoui.core import GeoIntent
from geoui.mcp._describe import describe
from geoui.mcp.server import mcp
from geoui.tools import (
    GET_STATE_DOC,
    RENDER_INTENT_DOC,
    GeoUIGetStateRequest,
    GeoUIGetStateResult,
    GeoUIRenderIntentRequest,
    GeoUIRenderIntentResult,
)

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "akd_contract.json").read_text())
GEOUI_TOOL_NAMES = {"geo_ui_render_intent_tool", "geo_ui_get_state_tool"}

SIMPLE_INTENT = {
    "viewport": {"bbox": [-125, 32, -114, 42], "crs": "EPSG:4326"},
    "time": {"instant": "2025-09-15"},
    "layers": [{"id": "MODIS_Aqua_Aerosol", "opacity": 0.8}],
}


@pytest.fixture
async def tools_by_name():
    async with Client(mcp) as client:
        return {t.name: t for t in await client.list_tools()}


class TestContract:
    async def test_exposes_exactly_the_two_protocol_tools(self, tools_by_name):
        assert set(tools_by_name) == GEOUI_TOOL_NAMES

    @pytest.mark.parametrize("name", sorted(GEOUI_TOOL_NAMES))
    async def test_input_schema_matches_akd(self, tools_by_name, name):
        ours, golden = tools_by_name[name].inputSchema, GOLDEN[name]["inputSchema"]
        assert list(ours["properties"]) == list(golden["properties"])
        assert ours.get("required") == golden.get("required")
        assert ours.get("additionalProperties") == golden.get("additionalProperties")

    @pytest.mark.parametrize("name", sorted(GEOUI_TOOL_NAMES))
    async def test_description_matches_akd(self, tools_by_name, name):
        assert tools_by_name[name].description == GOLDEN[name]["description"]

    @pytest.mark.parametrize("name", sorted(GEOUI_TOOL_NAMES))
    async def test_output_schema_drops_only_the_response_key(self, tools_by_name, name):
        golden_props = [p for p in GOLDEN[name]["outputSchema"]["properties"] if p != "_response"]
        assert list(tools_by_name[name].outputSchema["properties"]) == golden_props

    def test_describe_reproduces_akd_format(self):
        assert (
            describe(RENDER_INTENT_DOC, GeoUIRenderIntentRequest, GeoUIRenderIntentResult)
            == (GOLDEN["geo_ui_render_intent_tool"]["akd_description"])
        )
        assert (
            describe(GET_STATE_DOC, GeoUIGetStateRequest, GeoUIGetStateResult)
            == (GOLDEN["geo_ui_get_state_tool"]["akd_description"])
        )


class TestCalls:
    async def test_render_then_get_state_round_trip(self):
        async with Client(mcp) as client:
            rendered = await client.call_tool("geo_ui_render_intent_tool", {"intent": SIMPLE_INTENT})
            url = rendered.structured_content["url"]
            assert url.startswith("https://worldview.earthdata.nasa.gov/?")
            assert "t=2025-09-15" in url
            assert "_response" not in rendered.structured_content
            assert json.loads(rendered.content[0].text) == rendered.structured_content

            state = await client.call_tool("geo_ui_get_state_tool", {"url": url})
            intent = GeoIntent.model_validate(state.structured_content["intent"])
        assert intent.viewport.bbox == [-125, 32, -114, 42]
        assert {layer.id: layer.opacity for layer in intent.layers}["MODIS_Aqua_Aerosol"] == 0.8

    async def test_embed_mode_opt_in(self):
        async with Client(mcp) as client:
            rendered = await client.call_tool(
                "geo_ui_render_intent_tool", {"intent": SIMPLE_INTENT, "embed_mode": True}
            )
        assert "em=true" in rendered.structured_content["url"]

    async def test_invalid_crs_is_a_tool_error(self):
        bad = {**SIMPLE_INTENT, "viewport": {"bbox": [0, 0, 1, 1], "crs": "EPSG:9999"}}
        async with Client(mcp) as client:
            with pytest.raises(ToolError):
                await client.call_tool("geo_ui_render_intent_tool", {"intent": bad})


@pytest.mark.integration
async def test_stdio_smoke():
    """Spawn the server as a subprocess over stdio and list its tools."""
    server_path = Path(__file__).resolve().parents[2] / "geoui" / "mcp" / "server.py"
    async with Client(str(server_path)) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == GEOUI_TOOL_NAMES
