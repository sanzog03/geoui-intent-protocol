"""pydantic-ai toolsets for the tools the demo serves in-process.

- :data:`geoui_toolset` — the two GeoUI protocol tools. Same names,
  descriptions and parameters as the MCP server in ``worldview.mcp`` so logs
  stay comparable across both paths.
- :data:`permalink_toolset` — ``worldview_permalink_tool``, the pre-protocol
  way to build a Worldview URL from explicit parameters; the baseline skill
  calls it and the GeoUI skill lists it as superseded.

Protocol violations (undeclared extension, unsupported CRS, instant vs range,
unparsable URL) are raised as :class:`pydantic_ai.ModelRetry` so the model
gets the message back as a retry prompt instead of the turn aborting.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, ValidationError
from pydantic_ai import ModelRetry
from pydantic_ai.toolsets import FunctionToolset

from geoui.core import GeoIntent
from worldview.adapter import WorldviewPermalinkInputSchema, build_url, intent_to_url, url_to_intent
from worldview.tools import (
    EMBED_MODE_DESCRIPTION,
    GET_STATE_DOC,
    INTENT_FIELD_DESCRIPTION,
    LIST_INTENT_EXTENSIONS_DOC,
    RENDER_INTENT_DOC,
    URL_IN_DESCRIPTION,
    list_intent_extensions,
    prepare_intent,
)

PERMALINK_DOC = (
    "Build a NASA Worldview permalink URL from explicit parameters: layers (GIBS layer ids "
    "with optional opacity / palette / min / max), projection, a date or datetime, a bbox, "
    'and optional compare and chart settings. Returns {"url": ...}. When the GeoUI protocol '
    "tools are available, prefer geo_ui_render_intent_tool and describe the state as a GeoIntent."
)

geoui_toolset: FunctionToolset = FunctionToolset(id="geoui")
permalink_toolset: FunctionToolset = FunctionToolset(id="worldview-permalink")


@geoui_toolset.tool_plain(name="geo_ui_render_intent_tool", description=RENDER_INTENT_DOC)
async def geo_ui_render_intent_tool(
    intent: Annotated[GeoIntent, Field(description=INTENT_FIELD_DESCRIPTION)],
    embed_mode: Annotated[bool, Field(description=EMBED_MODE_DESCRIPTION)] = False,
) -> dict[str, str]:
    try:
        return {"url": intent_to_url(prepare_intent(intent), embed_mode=embed_mode)}
    except ValueError as e:
        raise ModelRetry(str(e)) from e


@geoui_toolset.tool_plain(name="geo_ui_get_state_tool", description=GET_STATE_DOC)
async def geo_ui_get_state_tool(url: Annotated[str, Field(description=URL_IN_DESCRIPTION)]) -> dict[str, object]:
    try:
        return {"intent": url_to_intent(url).model_dump(by_alias=True, exclude_none=True)}
    except ValueError as e:
        raise ModelRetry(str(e)) from e


@geoui_toolset.tool_plain(name="geo_ui_list_intent_extensions_tool", description=LIST_INTENT_EXTENSIONS_DOC)
async def geo_ui_list_intent_extensions_tool() -> dict[str, object]:
    return {"extensions": [e.model_dump() for e in list_intent_extensions()]}


@permalink_toolset.tool_plain(name="worldview_permalink_tool", description=PERMALINK_DOC)
async def worldview_permalink_tool(params: WorldviewPermalinkInputSchema) -> dict[str, str]:
    try:
        return {"url": build_url(params)}
    except (ValidationError, ValueError) as e:
        raise ModelRetry(str(e)) from e


__all__ = [
    "PERMALINK_DOC",
    "geo_ui_get_state_tool",
    "geo_ui_list_intent_extensions_tool",
    "geo_ui_render_intent_tool",
    "geoui_toolset",
    "permalink_toolset",
    "worldview_permalink_tool",
]
