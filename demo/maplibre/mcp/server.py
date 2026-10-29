"""FastMCP server for the GeoUI Intent Protocol over CDP.

Exposes ``geo_ui_render_intent_tool``, ``geo_ui_get_state_tool`` and
``geo_ui_list_intent_extensions_tool`` (the same names and shapes as the
Worldview adapter's server) for whatever page exposes ``window.geoui`` in the
Chromium at ``PLAYWRIGHT_CDP_ENDPOINT`` (``GEOUI_APP_URL`` says which page,
and is opened when none is found). One CDP connection lives for the server's
lifetime and reconnects if the browser went away.

Run locally::

    maplibre-mcp                      # stdio (default)
    maplibre-mcp --transport http --port 8001

or register it in Claude Code's ``.mcp.json`` as a stdio server.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from geoui.core import GeoIntent
from maplibre import tools
from maplibre.cdp import BridgeConfig, BridgeSession, GeoUISession, config_from_env
from maplibre.mcp._describe import describe


class SessionHolder:
    """One session for the server's lifetime, opened on first use and reopened if its connection dropped."""

    def __init__(self, factory: tools.SessionFactory) -> None:
        self._factory = factory
        self._cm: AbstractAsyncContextManager[GeoUISession] | None = None
        self._session: GeoUISession | None = None

    async def get(self) -> GeoUISession:
        if self._session is not None and isinstance(self._session, BridgeSession) and not self._session.connected:
            await self.close()
        if self._session is None:
            self._cm = self._factory()
            self._session = await self._cm.__aenter__()
        return self._session

    async def close(self) -> None:
        cm, self._cm, self._session = self._cm, None, None
        if cm is not None:
            await cm.__aexit__(None, None, None)


def create_server(
    config: BridgeConfig | None = None, *, session_factory: tools.SessionFactory | None = None
) -> FastMCP:
    holder = SessionHolder(session_factory or tools.default_session_factory(config))

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        try:
            yield {}
        finally:
            await holder.close()

    mcp = FastMCP("geoui", lifespan=lifespan)

    async def geo_ui_render_intent_tool(intent: GeoIntent) -> tools.GeoUIRenderIntentResult:
        return await tools.render_intent(await holder.get(), intent)

    async def geo_ui_get_state_tool() -> tools.GeoUIGetStateResult:
        return await tools.get_state(await holder.get())

    async def geo_ui_list_intent_extensions_tool() -> tools.GeoUIListIntentExtensionsResult:
        return await tools.list_intent_extensions(await holder.get())

    mcp.tool(
        geo_ui_render_intent_tool,
        name="geo_ui_render_intent_tool",
        description=describe(tools.RENDER_INTENT_DOC, tools.GeoUIRenderIntentRequest, tools.GeoUIRenderIntentResult),
    )
    mcp.tool(
        geo_ui_get_state_tool,
        name="geo_ui_get_state_tool",
        description=describe(tools.GET_STATE_DOC, tools.GeoUIGetStateRequest, tools.GeoUIGetStateResult),
    )
    mcp.tool(
        geo_ui_list_intent_extensions_tool,
        name="geo_ui_list_intent_extensions_tool",
        description=describe(
            tools.LIST_INTENT_EXTENSIONS_DOC,
            tools.GeoUIListIntentExtensionsRequest,
            tools.GeoUIListIntentExtensionsResult,
        ),
    )
    mcp.holder = holder  # type: ignore[attr-defined]  # for tests and for main() to close
    return mcp


#: The server the console script and ``fastmcp run`` use (configured from the environment, connects lazily).
mcp = create_server(config_from_env())


def main(argv: list[str] | None = None) -> None:
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the GeoUI MCP server over CDP")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport (default: stdio, or MCP_TRANSPORT env var)",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"), help="Bind host for http/sse")
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8001")), help="Port for http/sse")
    args = parser.parse_args(argv)

    server = create_server(config_from_env())  # after load_dotenv, so .env values count
    if args.transport == "stdio":
        server.run()
    else:
        server.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
