"""Contract tests for the CDP-bridge MCP server.

``fixtures/bridge_contract.json`` is the golden tool contract (names, input
schemas, descriptions); regenerate it deliberately with
``uv run python scripts/dump_mcp_contract.py local --module maplibre.mcp.server:mcp --golden
demo/maplibre/tests/mcp/fixtures/bridge_contract.json --update-golden`` and review the diff.
The tool names are the Worldview server's, so an agent prompt works against either.
"""

import json
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from maplibre.mcp.server import create_server

from .._fake_session import FakeSession

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "bridge_contract.json").read_text())
GEOUI_TOOL_NAMES = {"geo_ui_render_intent_tool", "geo_ui_get_state_tool", "geo_ui_list_intent_extensions_tool"}


@pytest.fixture
def page():
    return FakeSession()


@pytest.fixture
def server(page):
    return create_server(session_factory=page.factory())


class TestContract:
    async def test_exposes_exactly_the_protocol_tools(self, server):
        async with Client(server) as client:
            assert {t.name for t in await client.list_tools()} == GEOUI_TOOL_NAMES

    @pytest.mark.parametrize("name", sorted(GEOUI_TOOL_NAMES))
    async def test_input_schema_and_description_match_the_golden(self, server, name):
        async with Client(server) as client:
            tool = {t.name: t for t in await client.list_tools()}[name]
        assert tool.inputSchema == GOLDEN[name]["inputSchema"]
        assert tool.description == GOLDEN[name]["description"]

    def test_tool_names_equal_the_worldview_servers(self):
        worldview = json.loads(
            (Path(__file__).resolve().parents[4] / "demo/worldview/tests/mcp/fixtures/akd_contract.json").read_text()
        )
        assert set(worldview) == GEOUI_TOOL_NAMES == set(GOLDEN)


class TestCalls:
    async def test_list_then_render_then_get_state(self, server, page):
        async with Client(server) as client:
            listed = await client.call_tool("geo_ui_list_intent_extensions_tool", {})
            assert [e["name"] for e in listed.structured_content["extensions"]] == ["compare", "raster-styling"]
            assert [layer["id"] for layer in listed.structured_content["layers"]] == ["A", "B"]
            rendered = await client.call_tool(
                "geo_ui_render_intent_tool",
                {
                    "intent": {
                        "time": {"instant": "2025-09-15"},
                        "layers": [{"id": "A"}],
                        "compare:layers": [{"id": "B"}],
                    }
                },
            )
            assert rendered.structured_content["settled"] is True
            state = await client.call_tool("geo_ui_get_state_tool", {})
        assert state.structured_content["intent"]["time"]["instant"] == "2025-09-15"
        assert state.structured_content["intent"]["compare:layers"] == [{"id": "B"}]
        assert page.opened == 1  # one session for the server's lifetime

    async def test_refusals_reach_the_client_with_the_message(self, server):
        async with Client(server) as client:
            with pytest.raises(ToolError, match="not available in this app"):
                await client.call_tool("geo_ui_render_intent_tool", {"intent": {"chart:layer": "A"}})
            with pytest.raises(ToolError, match="unknown layer id"):
                await client.call_tool("geo_ui_render_intent_tool", {"intent": {"layers": [{"id": "Z"}]}})


@pytest.mark.integration
async def test_stdio_smoke():
    """Spawn the console script over stdio and list its tools (no browser needed: the connection is lazy)."""
    from fastmcp.client.transports import StdioTransport

    async with Client(StdioTransport("uv", ["run", "maplibre-mcp"])) as client:
        assert {t.name for t in await client.list_tools()} == GEOUI_TOOL_NAMES
