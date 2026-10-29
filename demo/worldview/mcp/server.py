"""FastMCP server for the GeoUI Intent Protocol (Worldview reference adapter).

Exposes the protocol tools ``geo_ui_render_intent_tool`` and
``geo_ui_get_state_tool`` (names and shapes as the original akd-ext
deployment, with the intent description now generated from the adapter's
supported extensions) plus ``geo_ui_list_intent_extensions_tool``, the
deployment's extension catalogue.

Run locally::

    worldview-mcp                      # stdio (default)
    worldview-mcp --transport http --port 8000

or with the FastMCP CLI / FastMCP Cloud via ``fastmcp.json`` at the repo root
(entrypoint ``demo/worldview/mcp/server.py:mcp``).
"""

from __future__ import annotations

import argparse
import os

from fastmcp import FastMCP

from worldview import tools
from worldview.mcp._describe import describe

mcp = FastMCP("geoui")

mcp.tool(
    tools.geo_ui_render_intent_tool,
    name="geo_ui_render_intent_tool",
    description=describe(tools.RENDER_INTENT_DOC, tools.GeoUIRenderIntentRequest, tools.GeoUIRenderIntentResult),
)
mcp.tool(
    tools.geo_ui_get_state_tool,
    name="geo_ui_get_state_tool",
    description=describe(tools.GET_STATE_DOC, tools.GeoUIGetStateRequest, tools.GeoUIGetStateResult),
)
mcp.tool(
    tools.geo_ui_list_intent_extensions_tool,
    name="geo_ui_list_intent_extensions_tool",
    description=describe(
        tools.LIST_INTENT_EXTENSIONS_DOC, tools.GeoUIListIntentExtensionsRequest, tools.GeoUIListIntentExtensionsResult
    ),
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the GeoUI MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport (default: stdio, or MCP_TRANSPORT env var)",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"), help="Bind host for http/sse")
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8000")), help="Port for http/sse")
    args = parser.parse_args(argv)

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
