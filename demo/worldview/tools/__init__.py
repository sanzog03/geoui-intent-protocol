"""Framework-agnostic surface of the GeoUI protocol tools for Worldview.

Three operations at the adapter boundary:

- ``geo_ui_render_intent_tool`` — agent → application. Takes a ``GeoIntent``
  and returns a handle the application can open (for Worldview, a URL).
- ``geo_ui_get_state_tool`` — application → agent. Takes the handle and
  returns the application state as a ``GeoIntent``.
- ``geo_ui_list_intent_extensions_tool`` — what this deployment supports.
  Lists the intent extensions the adapter implements, with their fields,
  so the agent decides which ones a request needs and fills their fields.

Extensions are **pre-declared** by the render tool: the agent never writes
``geoui_extensions``. :func:`prepare_intent` adds the supported URIs to every
incoming intent and refuses namespaced fields of extensions outside
``SUPPORTED_EXTENSIONS`` (owned by the adapter), so the document handed to
the adapter is always conforming and the capability list is one place.

This module holds the request/response models, the agent-facing docstrings
and the plain async functions. It depends only on pydantic. ``worldview.mcp``
serves these over MCP; ``worldview.tools.pai`` exposes them as a pydantic-ai
toolset. All three must keep the same names, parameter shapes and
descriptions so logs and benchmarks stay comparable.
"""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel, Field

from geoui.core import GeoIntent
from geoui.extensions import declare, used_prefixes
from worldview.adapter import SUPPORTED_EXTENSIONS, intent_to_url, url_to_intent

SUPPORTED_EXTENSION_URIS: tuple[str, ...] = tuple(spec.uri for spec in SUPPORTED_EXTENSIONS)
SUPPORTED_EXTENSION_NAMES: tuple[str, ...] = tuple(spec.prefix for spec in SUPPORTED_EXTENSIONS)

# -----------------------------------------------------------------------------
# Agent-facing text. The render / get-state docs are kept verbatim from the
# original akd tools; the intent field description and the list tool are
# generated from SUPPORTED_EXTENSIONS so they can never disagree with it.
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

LIST_INTENT_EXTENSIONS_DOC = inspect.cleandoc(
    """List the intent extensions this Worldview deployment supports.

    Each entry names an extension (compare, chart, raster-styling, ...), says
    where its fields live (`scope`: "intent" = namespaced keys on the GeoIntent
    root, "layer" = namespaced keys on each LayerRef), gives a one-line
    summary of when to use it, its namespaced `keys`, which of them are
    `required`, and the JSON schema of its fields.

    Decide which extensions the user's request needs, then fill only their
    namespaced fields in the GeoIntent you pass to geo_ui_render_intent_tool.
    Supported extensions are pre-declared by that tool, so never write
    `geoui_extensions` yourself; fields of an unsupported extension are
    rejected.
    """
)


def _extension_keys(spec: Any) -> str:
    keys = ", ".join(spec.keys())
    return f"on each LayerRef: {keys}" if spec.scope == "layer" else keys


def _extensions_sentence() -> str:
    parts = "; ".join(f"{spec.prefix} → {_extension_keys(spec)}" for spec in SUPPORTED_EXTENSIONS)
    return (
        "Extensions are pre-declared by this tool: do not write `geoui_extensions`; just add the namespaced "
        f"fields of the extensions the request needs. Supported: {parts}. "
        "Call geo_ui_list_intent_extensions_tool for their field types."
    )


INTENT_FIELD_DESCRIPTION = (
    "GeoIntent describing the desired application state. "
    "Core fields: viewport (bbox + crs), time (instant), layers (id + visible + opacity). " + _extensions_sentence()
)

EMBED_MODE_DESCRIPTION = (
    "If True, opens Worldview in embed mode (em=true): minimal chrome intended "
    "for iframes, with most UI controls hidden. Default False opens the full "
    "interactive Worldview app."
)

URL_OUT_DESCRIPTION = "Worldview permalink URL that opens the map at the requested state."
URL_IN_DESCRIPTION = "Worldview permalink URL to parse."
INTENT_OUT_DESCRIPTION = "GeoIntent describing the application state encoded in the URL."
EXTENSIONS_OUT_DESCRIPTION = "The supported intent extensions, in the order the deployment lists them."


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


class IntentExtension(BaseModel):
    """One supported extension, as ``ExtensionSpec.describe()`` lays it out."""

    name: str = Field(description="The namespace prefix, e.g. compare.")
    uri: str = Field(description="The extension's canonical, versioned URI.")
    scope: str = Field(description='"intent": keys on the GeoIntent root; "layer": keys on each LayerRef.')
    summary: str = Field(description="When to use it, in one line.")
    keys: list[str] = Field(description="The namespaced keys, e.g. compare:layers.")
    required: list[str] = Field(description="Keys that must be present once the extension is used.")
    fields_schema: dict[str, Any] = Field(description="JSON schema of the fields (without the prefix).")


class GeoUIListIntentExtensionsRequest(BaseModel):
    """Input for ``GeoUIListIntentExtensionsTool`` (none)."""


class GeoUIListIntentExtensionsResult(BaseModel):
    """Output for ``GeoUIListIntentExtensionsTool``."""

    extensions: list[IntentExtension] = Field(..., description=EXTENSIONS_OUT_DESCRIPTION)


# -----------------------------------------------------------------------------
# Pre-declaration
# -----------------------------------------------------------------------------


def prepare_intent(intent: GeoIntent) -> GeoIntent:
    """The document the adapter receives: supported URIs declared, unsupported namespaces refused.

    Raises ``ValueError`` naming the unsupported extension(s) and the supported
    ones, so an agent can recover.
    """
    unsupported = sorted(used_prefixes(intent) - set(SUPPORTED_EXTENSION_NAMES))
    if unsupported:
        raise ValueError(
            f"extension(s) {unsupported} are not available in this deployment; "
            f"supported: {', '.join(SUPPORTED_EXTENSION_NAMES)} (see geo_ui_list_intent_extensions_tool)"
        )
    return declare(intent, SUPPORTED_EXTENSION_URIS)


def list_intent_extensions() -> list[IntentExtension]:
    return [IntentExtension.model_validate(spec.describe()) for spec in SUPPORTED_EXTENSIONS]


# -----------------------------------------------------------------------------
# The operations. Parameter names and order match the MCP input schema.
# -----------------------------------------------------------------------------


async def geo_ui_render_intent_tool(intent: GeoIntent, embed_mode: bool = False) -> GeoUIRenderIntentResult:
    return GeoUIRenderIntentResult(url=intent_to_url(prepare_intent(intent), embed_mode=embed_mode))


async def geo_ui_get_state_tool(url: str) -> GeoUIGetStateResult:
    return GeoUIGetStateResult(intent=url_to_intent(url))


async def geo_ui_list_intent_extensions_tool() -> GeoUIListIntentExtensionsResult:
    return GeoUIListIntentExtensionsResult(extensions=list_intent_extensions())


geo_ui_render_intent_tool.__doc__ = RENDER_INTENT_DOC
geo_ui_get_state_tool.__doc__ = GET_STATE_DOC
geo_ui_list_intent_extensions_tool.__doc__ = LIST_INTENT_EXTENSIONS_DOC

__all__ = [
    "EMBED_MODE_DESCRIPTION",
    "EXTENSIONS_OUT_DESCRIPTION",
    "GET_STATE_DOC",
    "INTENT_FIELD_DESCRIPTION",
    "INTENT_OUT_DESCRIPTION",
    "LIST_INTENT_EXTENSIONS_DOC",
    "RENDER_INTENT_DOC",
    "SUPPORTED_EXTENSION_NAMES",
    "SUPPORTED_EXTENSION_URIS",
    "URL_IN_DESCRIPTION",
    "URL_OUT_DESCRIPTION",
    "GeoUIGetStateRequest",
    "GeoUIGetStateResult",
    "GeoUIListIntentExtensionsRequest",
    "GeoUIListIntentExtensionsResult",
    "GeoUIRenderIntentRequest",
    "GeoUIRenderIntentResult",
    "IntentExtension",
    "geo_ui_get_state_tool",
    "geo_ui_list_intent_extensions_tool",
    "geo_ui_render_intent_tool",
    "list_intent_extensions",
    "prepare_intent",
]
