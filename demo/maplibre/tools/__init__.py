"""Framework-agnostic surface of the GeoUI protocol tools for a ``window.geoui`` page.

The same three operations as the Worldview adapter's tool layer, with the
same names, so logs and benchmarks compare across mechanisms:

- ``geo_ui_render_intent_tool`` — agent → application. Takes a ``GeoIntent``,
  renders it in the page and returns the state the page settled on.
- ``geo_ui_get_state_tool`` — application → agent. Returns the page's state
  as a ``GeoIntent``.
- ``geo_ui_list_intent_extensions_tool`` — what this page supports: the
  extensions it attached and the layers it can show.

Nothing here is Worldview- or MapLibre-specific: the page's catalogue says
what is supported, :mod:`maplibre.catalogue` checks it against the
library and pre-declares the URIs, and a :class:`~maplibre.cdp.GeoUISession`
carries the calls. ``maplibre.mcp`` serves these over MCP;
``maplibre.tools.pai`` exposes them as a pydantic-ai toolset.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from pydantic import BaseModel, Field

from geoui.core import GeoIntent
from maplibre.catalogue import Catalogue, IntentExtension, LayerEntry, check_catalogue, prepare_intent
from maplibre.cdp import BridgeConfig, GeoUISession, bridge, config_from_env

#: Yields a session for one block of calls; ``default_session_factory`` opens a CDP connection per block.
SessionFactory = Callable[[], AbstractAsyncContextManager[GeoUISession]]


def default_session_factory(config: BridgeConfig | None = None) -> SessionFactory:
    cfg = config or config_from_env()
    return lambda: bridge(cfg)


# -----------------------------------------------------------------------------
# Agent-facing text
# -----------------------------------------------------------------------------

RENDER_INTENT_DOC = inspect.cleandoc(
    """Render a GeoIntent in the open map application.

    Use this tool to materialise the agent's intended application state
    (expressed as a GeoIntent) on screen. The agent reasons in GeoIntent
    terms, not in the application's own controls. Rendering REPLACES the
    whole state: fields you leave out return to the application's defaults
    (compare off, styling cleared, default time and extent), so read the
    state first and resend what must stay. Returns the state the
    application settled on.
    """
)

GET_STATE_DOC = inspect.cleandoc(
    """Read the current application state as a GeoIntent.

    Use this to observe what is on screen — typically when continuing an
    iterative analysis: read current state, decide what to change, emit a
    new GeoIntent via geo_ui_render_intent_tool. The user may have changed
    the view by hand since your last render.
    """
)

LIST_INTENT_EXTENSIONS_DOC = inspect.cleandoc(
    """List the intent extensions and the layers this application supports.

    Call this first in a conversation. Each extension entry names it
    (compare, raster-styling, ...), says where its fields live (`scope`:
    "intent" = namespaced keys on the GeoIntent root, "layer" = namespaced
    keys on each LayerRef), gives a one-line summary of when to use it, its
    namespaced `keys`, which of them are `required`, and the JSON schema of
    its fields. `layers` lists the layer ids the application can show, with
    titles and temporal coverage; a GeoIntent may only reference those ids.

    Decide which extensions the user's request needs, then fill only their
    namespaced fields in the GeoIntent you pass to geo_ui_render_intent_tool.
    Supported extensions are pre-declared by that tool, so never write
    `geoui_extensions` yourself; fields of an unsupported extension and
    unknown layer ids are rejected.
    """
)

INTENT_FIELD_DESCRIPTION = (
    "GeoIntent describing the desired application state. "
    "Core fields: viewport (bbox [west, south, east, north] in degrees, crs EPSG:4326), "
    "time (instant, ISO date), layers (id + visible + opacity). "
    "Extensions and the layer catalogue come from the application: call geo_ui_list_intent_extensions_tool "
    "first. Supported extensions are pre-declared by this tool: do not write `geoui_extensions`; just add the "
    "namespaced fields the request needs. Fields of an unsupported extension and unknown layer ids are rejected. "
    "Rendering replaces the whole state."
)

INTENT_OUT_DESCRIPTION = "GeoIntent describing the application state."
SETTLED_OUT_DESCRIPTION = (
    "True when the application confirmed the state was applied on screen; false when it timed out waiting."
)
EXTENSIONS_OUT_DESCRIPTION = "The supported intent extensions, in the order the application lists them."
LAYERS_OUT_DESCRIPTION = "The layers the application can show; GeoIntent layer ids must come from here."


# -----------------------------------------------------------------------------
# Request / response models
# -----------------------------------------------------------------------------


class GeoUIRenderIntentRequest(BaseModel):
    """Input for ``geo_ui_render_intent_tool``."""

    intent: GeoIntent = Field(..., description=INTENT_FIELD_DESCRIPTION)


class GeoUIRenderIntentResult(BaseModel):
    """Output for ``geo_ui_render_intent_tool``."""

    intent: GeoIntent = Field(..., description=INTENT_OUT_DESCRIPTION)
    settled: bool = Field(default=True, description=SETTLED_OUT_DESCRIPTION)


class GeoUIGetStateRequest(BaseModel):
    """Input for ``geo_ui_get_state_tool`` (none)."""


class GeoUIGetStateResult(BaseModel):
    """Output for ``geo_ui_get_state_tool``."""

    intent: GeoIntent = Field(..., description=INTENT_OUT_DESCRIPTION)


class GeoUIListIntentExtensionsRequest(BaseModel):
    """Input for ``geo_ui_list_intent_extensions_tool`` (none)."""


class GeoUIListIntentExtensionsResult(BaseModel):
    """Output for ``geo_ui_list_intent_extensions_tool``."""

    extensions: list[IntentExtension] = Field(..., description=EXTENSIONS_OUT_DESCRIPTION)
    layers: list[LayerEntry] = Field(default_factory=list, description=LAYERS_OUT_DESCRIPTION)


# -----------------------------------------------------------------------------
# The operations, against a session
# -----------------------------------------------------------------------------


async def catalogue_of(session: GeoUISession) -> Catalogue:
    """The page's catalogue, checked against this library."""
    catalogue = Catalogue.model_validate(await session.describe())
    check_catalogue(catalogue)
    return catalogue


def intent_payload(intent: GeoIntent) -> dict[str, Any]:
    """What crosses ``page.evaluate``: JSON, with ``None`` fields left out (the page treats absent as default)."""
    return intent.model_dump(mode="json", by_alias=True, exclude_none=True)


async def render_intent(session: GeoUISession, intent: GeoIntent) -> GeoUIRenderIntentResult:
    catalogue = await catalogue_of(session)
    prepared = prepare_intent(intent, catalogue)  # ValueError → the agent's retry message
    result = await session.render(intent_payload(prepared))
    return GeoUIRenderIntentResult(
        intent=GeoIntent.model_validate(result["state"]), settled=bool(result.get("settled", True))
    )


async def get_state(session: GeoUISession) -> GeoUIGetStateResult:
    return GeoUIGetStateResult(intent=GeoIntent.model_validate(await session.get_state()))


async def list_intent_extensions(session: GeoUISession) -> GeoUIListIntentExtensionsResult:
    catalogue = await catalogue_of(session)
    return GeoUIListIntentExtensionsResult(extensions=catalogue.extensions, layers=catalogue.layers)


__all__ = [
    "EXTENSIONS_OUT_DESCRIPTION",
    "GET_STATE_DOC",
    "INTENT_FIELD_DESCRIPTION",
    "INTENT_OUT_DESCRIPTION",
    "LAYERS_OUT_DESCRIPTION",
    "LIST_INTENT_EXTENSIONS_DOC",
    "RENDER_INTENT_DOC",
    "SETTLED_OUT_DESCRIPTION",
    "GeoUIGetStateRequest",
    "GeoUIGetStateResult",
    "GeoUIListIntentExtensionsRequest",
    "GeoUIListIntentExtensionsResult",
    "GeoUIRenderIntentRequest",
    "GeoUIRenderIntentResult",
    "SessionFactory",
    "catalogue_of",
    "default_session_factory",
    "get_state",
    "intent_payload",
    "list_intent_extensions",
    "render_intent",
]
