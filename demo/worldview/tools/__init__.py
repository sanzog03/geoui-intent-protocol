"""Framework-agnostic surface of the two GeoUI protocol tools.

The protocol exposes exactly two operations at the adapter boundary:

- ``geo_ui_render_intent_tool`` — agent → application. Takes a ``GeoIntent``
  and returns a handle the application can open (for Worldview, a URL).
- ``geo_ui_get_state_tool`` — application → agent. Takes the handle and
  returns the application state as a ``GeoIntent``.

This module holds the request/response models, the agent-facing docstrings
and the plain async functions. It depends only on pydantic. ``worldview.mcp``
serves these over MCP; ``worldview.tools.pai`` exposes them as a pydantic-ai
toolset. All three must keep the same names, parameter shapes and
descriptions so logs and benchmarks stay comparable.
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel, Field

from geoui.core import GeoIntent
from worldview.adapter import intent_to_url, url_to_intent

# -----------------------------------------------------------------------------
# Agent-facing text. Kept verbatim from the original akd tools so the MCP
# contract (tool descriptions) does not drift.
# -----------------------------------------------------------------------------

RENDER_INTENT_DOC = inspect.cleandoc(
    """Render a GeoIntent as a NASA Worldview permalink URL.

    Use this tool to materialise the agent's intended application state
    (expressed as a GeoIntent) into a URL the user can open. The agent
    reasons in GeoIntent terms, not Worldview-specific URL params.
    """
)

GET_STATE_DOC = inspect.cleandoc(
    """Read the current Worldview application state as a GeoIntent.

    Use this to observe the state implied by a Worldview URL — typically
    when continuing an iterative analysis: read current state, decide
    what to change, emit a new GeoIntent via ``geoui_render_intent``.

    Auto-injected base reflectance and reference overlay layers are
    preserved in the output for fidelity; ignore them when computing
    refinements.
    """
)

INTENT_FIELD_DESCRIPTION = (
    "GeoIntent describing the desired application state. "
    "Core fields: viewport (bbox + crs), time (instant), layers (id + visible + opacity). "
    "Use extensions by adding their URI to `geoui_extensions` and including the "
    "corresponding namespaced fields: "
    "geoui:compare/v1.0.0 → compare:layers, compare:time, compare:mode, "
    "compare:value, compare:active_side; "
    "geoui:chart/v1.0.0 → chart:layer, chart:area, chart:time, chart:autoload; "
    "geoui:raster-styling/v1.0.0 → on each LayerRef: raster-styling:palettes, "
    "raster-styling:min, raster-styling:max, raster-styling:squash, raster-styling:style."
)

EMBED_MODE_DESCRIPTION = (
    "If True, opens Worldview in embed mode (em=true): minimal chrome intended "
    "for iframes, with most UI controls hidden. Default False opens the full "
    "interactive Worldview app."
)

URL_OUT_DESCRIPTION = "Worldview permalink URL that opens the map at the requested state."
URL_IN_DESCRIPTION = "Worldview permalink URL to parse."
INTENT_OUT_DESCRIPTION = "GeoIntent describing the application state encoded in the URL."


# -----------------------------------------------------------------------------
# Request / response models
# -----------------------------------------------------------------------------


class GeoUIRenderIntentRequest(BaseModel):
    """Input for ``GeoUIRenderIntentTool``."""

    intent: GeoIntent = Field(..., description=INTENT_FIELD_DESCRIPTION)
    embed_mode: bool = Field(default=False, description=EMBED_MODE_DESCRIPTION)


class GeoUIRenderIntentResult(BaseModel):
    """Output for ``GeoUIRenderIntentTool``."""

    url: str = Field(..., description=URL_OUT_DESCRIPTION)


class GeoUIGetStateRequest(BaseModel):
    """Input for ``GeoUIGetStateTool``."""

    url: str = Field(..., description=URL_IN_DESCRIPTION)


class GeoUIGetStateResult(BaseModel):
    """Output for ``GeoUIGetStateTool``."""

    intent: GeoIntent = Field(..., description=INTENT_OUT_DESCRIPTION)


# -----------------------------------------------------------------------------
# The two operations. Parameter names and order match the MCP input schema.
# -----------------------------------------------------------------------------


async def geo_ui_render_intent_tool(intent: GeoIntent, embed_mode: bool = False) -> GeoUIRenderIntentResult:
    return GeoUIRenderIntentResult(url=intent_to_url(intent, embed_mode=embed_mode))


async def geo_ui_get_state_tool(url: str) -> GeoUIGetStateResult:
    return GeoUIGetStateResult(intent=url_to_intent(url))


geo_ui_render_intent_tool.__doc__ = RENDER_INTENT_DOC
geo_ui_get_state_tool.__doc__ = GET_STATE_DOC

__all__ = [
    "EMBED_MODE_DESCRIPTION",
    "GET_STATE_DOC",
    "INTENT_FIELD_DESCRIPTION",
    "INTENT_OUT_DESCRIPTION",
    "RENDER_INTENT_DOC",
    "URL_IN_DESCRIPTION",
    "URL_OUT_DESCRIPTION",
    "GeoUIGetStateRequest",
    "GeoUIGetStateResult",
    "GeoUIRenderIntentRequest",
    "GeoUIRenderIntentResult",
    "geo_ui_get_state_tool",
    "geo_ui_render_intent_tool",
]
