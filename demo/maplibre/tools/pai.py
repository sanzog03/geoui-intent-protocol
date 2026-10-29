"""The three GeoUI tools as a pydantic-ai ``FunctionToolset`` (in-process, no MCP server).

Same names, descriptions and parameters as ``maplibre.mcp`` so logs stay
comparable across both paths. A refused intent (unsupported extension,
unknown layer, bad CRS, incomplete extension fields, or the page saying no)
is raised as :class:`pydantic_ai.ModelRetry` so the model gets the message
back as a retry prompt instead of the turn aborting; a broken bridge
(:class:`~maplibre.cdp.BridgeError`) propagates, because the model cannot fix it.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelMessage
from pydantic_ai.toolsets import FunctionToolset

from geoui.core import GeoIntent
from maplibre.cdp import BridgeConfig
from maplibre.tools import (
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

LIST_TOOL = "geo_ui_list_intent_extensions_tool"
REPEATED_LIST_NOTE = (
    "The catalogue was returned by the previous tool result and does not change during a conversation, "
    "so it is not repeated. Do not call this tool again: answer the user now, or call geo_ui_get_state_tool "
    "/ geo_ui_render_intent_tool."
)


def last_tool_returned(messages: list[ModelMessage]) -> str | None:
    """Name of the most recent tool whose result the model has already seen (the current call excluded)."""
    for message in reversed(messages[:-1]):
        for part in reversed(message.parts):
            if part.part_kind == "tool-return":
                return part.tool_name
    return None


def make_geoui_toolset(
    config: BridgeConfig | None = None, *, session_factory: SessionFactory | None = None
) -> FunctionToolset:
    """A fresh toolset bound to ``config`` (or the environment); ``session_factory`` injects a fake for tests.

    The list tool is guarded against the one loop seen in practice: a reasoning
    model on Chat Completions re-issuing the no-argument catalogue call right
    after receiving the catalogue (its plan is not carried across tool calls).
    A back-to-back repeat gets a short note instead of the catalogue, which
    breaks the loop; a list after a render or get_state is answered in full.
    """
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

    @toolset.tool(name=LIST_TOOL, description=LIST_INTENT_EXTENSIONS_DOC)
    async def geo_ui_list_intent_extensions_tool(ctx: RunContext[Any]) -> dict[str, Any]:
        if last_tool_returned(ctx.messages) == LIST_TOOL:
            return {"note": REPEATED_LIST_NOTE}
        async with factory() as session:
            return (await list_intent_extensions(session)).model_dump(mode="json")

    return toolset


__all__ = ["LIST_TOOL", "REPEATED_LIST_NOTE", "last_tool_returned", "make_geoui_toolset"]
