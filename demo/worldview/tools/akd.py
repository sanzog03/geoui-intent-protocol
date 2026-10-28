"""akd ``BaseTool`` wrappers for the two GeoUI protocol tools.

Used by the IESO reference agents: a ``PydanticAIBaseAgentConfig`` accepts
akd ``BaseTool`` instances in its ``tools`` field and converts them to
pydantic_ai tools. Both tools are pure / no I/O and delegate to
``worldview.tools``. Names (``geo_ui_render_intent_tool`` /
``geo_ui_get_state_tool``) and descriptions are identical to the MCP server
in ``worldview.mcp`` so benchmark logs are comparable across both paths.

Requires akd-ext, installed with the ``geoui-worldview-demo`` project.
"""

from __future__ import annotations

from akd._base import InputSchema, OutputSchema
from akd._base.errors import SchemaValidationError
from akd.tools import BaseTool
from pydantic import Field

from geoui.core import GeoIntent
from worldview.adapter import intent_to_url, url_to_intent
from worldview.tools import (
    EMBED_MODE_DESCRIPTION,
    GET_STATE_DOC,
    INTENT_FIELD_DESCRIPTION,
    INTENT_OUT_DESCRIPTION,
    RENDER_INTENT_DOC,
    URL_IN_DESCRIPTION,
    URL_OUT_DESCRIPTION,
)

# -----------------------------------------------------------------------------
# render_intent
# -----------------------------------------------------------------------------


class GeoUIRenderIntentInputSchema(InputSchema):
    """Input for ``GeoUIRenderIntentTool``."""

    intent: GeoIntent = Field(..., description=INTENT_FIELD_DESCRIPTION)
    embed_mode: bool = Field(default=False, description=EMBED_MODE_DESCRIPTION)


class GeoUIRenderIntentOutputSchema(OutputSchema):
    """Output for ``GeoUIRenderIntentTool``."""

    url: str = Field(..., description=URL_OUT_DESCRIPTION)


class GeoUIRenderIntentTool(BaseTool[GeoUIRenderIntentInputSchema, GeoUIRenderIntentOutputSchema]):
    """Render a GeoIntent as a NASA Worldview permalink URL.

    Use this tool to materialise the agent's intended application state
    (expressed as a GeoIntent) into a URL the user can open. The agent
    reasons in GeoIntent terms, not Worldview-specific URL params.
    """

    __doc__ = RENDER_INTENT_DOC
    input_schema = GeoUIRenderIntentInputSchema
    output_schema = GeoUIRenderIntentOutputSchema

    async def _arun(self, params: GeoUIRenderIntentInputSchema) -> GeoUIRenderIntentOutputSchema:
        try:
            url = intent_to_url(params.intent, embed_mode=params.embed_mode)
        except ValueError as e:
            # Protocol violations (undeclared extension, unsupported CRS, instant vs
            # range, ...) must reach the model as a retry prompt so it can fix the
            # intent; akd-ext maps SchemaValidationError to pydantic_ai.ModelRetry.
            raise SchemaValidationError(str(e)) from e
        return GeoUIRenderIntentOutputSchema(url=url)


# -----------------------------------------------------------------------------
# get_state
# -----------------------------------------------------------------------------


class GeoUIGetStateInputSchema(InputSchema):
    """Input for ``GeoUIGetStateTool``."""

    url: str = Field(..., description=URL_IN_DESCRIPTION)


class GeoUIGetStateOutputSchema(OutputSchema):
    """Output for ``GeoUIGetStateTool``."""

    intent: GeoIntent = Field(..., description=INTENT_OUT_DESCRIPTION)


class GeoUIGetStateTool(BaseTool[GeoUIGetStateInputSchema, GeoUIGetStateOutputSchema]):
    """Read the current Worldview application state as a GeoIntent.

    Use this to observe the state implied by a Worldview URL — typically
    when continuing an iterative analysis: read current state, decide
    what to change, emit a new GeoIntent via ``geoui_render_intent``.

    Auto-injected base reflectance and reference overlay layers are
    preserved in the output for fidelity; ignore them when computing
    refinements.
    """

    __doc__ = GET_STATE_DOC
    input_schema = GeoUIGetStateInputSchema
    output_schema = GeoUIGetStateOutputSchema

    async def _arun(self, params: GeoUIGetStateInputSchema) -> GeoUIGetStateOutputSchema:
        try:
            intent = url_to_intent(params.url)
        except ValueError as e:
            raise SchemaValidationError(str(e)) from e  # see GeoUIRenderIntentTool._arun
        return GeoUIGetStateOutputSchema(intent=intent)
