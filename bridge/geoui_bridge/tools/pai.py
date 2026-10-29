"""The three GeoUI tools as a pydantic-ai ``FunctionToolset`` (in-process, no MCP server).

Same names, descriptions and parameters as ``geoui_bridge.mcp`` so logs stay
comparable across both paths. A refused intent (unsupported extension,
unknown layer, bad CRS, incomplete extension fields, or the page saying no)
is raised as :class:`pydantic_ai.ModelRetry` so the model gets the message
back as a retry prompt instead of the turn aborting; a broken bridge
(:class:`~geoui_bridge.cdp.BridgeError`) propagates, because the model cannot fix it.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import ModelRetry
from pydantic_ai.toolsets import FunctionToolset

from geoui.core import GeoIntent
from geoui_bridge.cdp import BridgeConfig
from geoui_bridge.tools import (
    GET_STATE_DOC,
    INTENT_FIELD_DESCRIPTION,
    LIST_INTENT_EXTENSIONS_DOC,
    RENDER_INTENT_DOC,
    SessionFactory,
    default_session_factory,
    get_state,
    list_intent_extensions,
    render_intent,
)


def make_geoui_toolset(
    config: BridgeConfig | None = None, *, session_factory: SessionFactory | None = None
) -> FunctionToolset:
    """A fresh toolset bound to ``config`` (or the environment); ``session_factory`` injects a fake for tests."""
    factory = session_factory or default_session_factory(config)
    toolset: FunctionToolset = FunctionToolset(id="geoui")

    @toolset.tool_plain(name="geo_ui_render_intent_tool", description=RENDER_INTENT_DOC)
    async def geo_ui_render_intent_tool(
        intent: Annotated[GeoIntent, Field(description=INTENT_FIELD_DESCRIPTION)],
    ) -> dict[str, Any]:
        async with factory() as session:
            try:
                return (await render_intent(session, intent)).model_dump(mode="json")
            except ValueError as e:
                raise ModelRetry(str(e)) from e

    @toolset.tool_plain(name="geo_ui_get_state_tool", description=GET_STATE_DOC)
    async def geo_ui_get_state_tool() -> dict[str, Any]:
        async with factory() as session:
            return (await get_state(session)).model_dump(mode="json")

    @toolset.tool_plain(name="geo_ui_list_intent_extensions_tool", description=LIST_INTENT_EXTENSIONS_DOC)
    async def geo_ui_list_intent_extensions_tool() -> dict[str, Any]:
        async with factory() as session:
            return (await list_intent_extensions(session)).model_dump(mode="json")

    return toolset


__all__ = ["make_geoui_toolset"]
