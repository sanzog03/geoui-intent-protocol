"""Contract tests for the standalone GeoUI MCP server.

The golden fixture ``fixtures/akd_contract.json`` was captured from the
akd-ext implementation (the one deployed on FastMCP Cloud) with an in-process
``fastmcp.Client``, then revised on 2026-10-28 when extensions became
pre-declared: the render tool's ``intent`` description is now generated from
the adapter's supported extensions and ``geo_ui_list_intent_extensions_tool``
was added. The standalone server must match the fixture's tool names, input
schemas and descriptions; regenerate it deliberately with
``uv run python scripts/dump_mcp_contract.py local --update-golden`` and
review the diff. (akd's ``OutputSchema`` leaked an empty ``_response`` key;
the fixture no longer carries it, and the output-schema test still tolerates
a golden that does.)
"""

import json
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from geoui.core import GeoIntent
from worldview.mcp._describe import describe
from worldview.mcp.server import mcp
from worldview.tools import (
    GET_STATE_DOC,
    LIST_INTENT_EXTENSIONS_DOC,
    RENDER_INTENT_DOC,
    GeoUIGetStateRequest,
    GeoUIGetStateResult,
    GeoUIListIntentExtensionsRequest,
    GeoUIListIntentExtensionsResult,
    GeoUIRenderIntentRequest,
    GeoUIRenderIntentResult,
)

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "akd_contract.json").read_text())
GEOUI_TOOL_NAMES = {"geo_ui_render_intent_tool", "geo_ui_get_state_tool", "geo_ui_list_intent_extensions_tool"}

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
    async def test_exposes_exactly_the_protocol_tools(self, tools_by_name):
        assert set(tools_by_name) == GEOUI_TOOL_NAMES

    @pytest.mark.parametrize("name", sorted(GEOUI_TOOL_NAMES))
    async def test_input_schema_matches_akd(self, tools_by_name, name):
        assert tools_by_name[name].inputSchema == GOLDEN[name]["inputSchema"]

    @pytest.mark.parametrize("name", sorted(GEOUI_TOOL_NAMES))
    async def test_description_matches_akd(self, tools_by_name, name):
        assert tools_by_name[name].description == GOLDEN[name]["description"]

    @pytest.mark.parametrize("name", sorted(GEOUI_TOOL_NAMES))
    async def test_output_schema_drops_only_the_response_key(self, tools_by_name, name):
        ours, golden = tools_by_name[name].outputSchema, GOLDEN[name]["outputSchema"]
        assert ours["properties"] == {k: v for k, v in golden["properties"].items() if k != "_response"}
        assert ours.get("required") == [k for k in golden.get("required", []) if k != "_response"]

    def test_describe_reproduces_akd_format(self):
        assert (
            describe(RENDER_INTENT_DOC, GeoUIRenderIntentRequest, GeoUIRenderIntentResult)
            == (GOLDEN["geo_ui_render_intent_tool"]["akd_description"])
        )
        assert (
            describe(GET_STATE_DOC, GeoUIGetStateRequest, GeoUIGetStateResult)
            == (GOLDEN["geo_ui_get_state_tool"]["akd_description"])
        )
        assert (
            describe(LIST_INTENT_EXTENSIONS_DOC, GeoUIListIntentExtensionsRequest, GeoUIListIntentExtensionsResult)
            == (GOLDEN["geo_ui_list_intent_extensions_tool"]["akd_description"])
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

    async def test_compare_fields_render_without_a_declaration(self):
        with_compare = {**SIMPLE_INTENT, "compare:layers": [{"id": "MODIS_Terra_Aerosol"}], "compare:mode": "spy"}
        async with Client(mcp) as client:
            rendered = await client.call_tool("geo_ui_render_intent_tool", {"intent": with_compare})
        assert "cm=spy" in rendered.structured_content["url"]

    async def test_unsupported_extension_is_a_tool_error(self):
        foreign = {**SIMPLE_INTENT, "elevation:exaggeration": 2}
        async with Client(mcp) as client:
            with pytest.raises(ToolError, match="not available in this deployment"):
                await client.call_tool("geo_ui_render_intent_tool", {"intent": foreign})

    async def test_list_intent_extensions_returns_the_catalogue(self):
        async with Client(mcp) as client:
            listed = await client.call_tool("geo_ui_list_intent_extensions_tool", {})
        names = [e["name"] for e in listed.structured_content["extensions"]]
        assert names == ["compare", "chart", "raster-styling"]
        assert listed.structured_content["extensions"][1]["required"] == ["chart:layer"]

    async def test_invalid_crs_is_a_tool_error(self):
        bad = {**SIMPLE_INTENT, "viewport": {"bbox": [0, 0, 1, 1], "crs": "EPSG:9999"}}
        async with Client(mcp) as client:
            with pytest.raises(ToolError):
                await client.call_tool("geo_ui_render_intent_tool", {"intent": bad})


@pytest.mark.integration
async def test_stdio_smoke():
    """Spawn the server as a subprocess over stdio and list its tools."""
    server_path = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
    async with Client(str(server_path)) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == GEOUI_TOOL_NAMES
