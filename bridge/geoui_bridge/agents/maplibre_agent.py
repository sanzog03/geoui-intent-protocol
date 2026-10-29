"""The MapLibre demo's agent: a bare pydantic-ai ``Agent`` with the three GeoUI tools and nothing else.

No skill, no discovery MCPs, no browser tools: the page's catalogue (through
``geo_ui_list_intent_extensions_tool``) is all the agent needs to know about
the application, and the bridge drives the browser. The same shape as the
Worldview GeoUI agent (model, reasoning effort, structured-or-text output,
``final_result_<ClassName>`` output tools) so benchmark runs compare.

Smoke test (one LLM call; ``OPENAI_API_KEY`` from ``.env``, the app at
``GEOUI_APP_URL``, Chromium on ``PLAYWRIGHT_CDP_ENDPOINT``)::

    uv run python -m geoui_bridge.agents.maplibre_agent "Show MODIS Aqua AOD over California on 2025-09-15"
"""

from __future__ import annotations

import inspect
import os
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.capabilities import AbstractCapability, Thinking

from geoui_bridge.cdp import BridgeConfig, config_from_env
from geoui_bridge.tools import SessionFactory
from geoui_bridge.tools.pai import make_geoui_toolset

AGENT_NAME = "maplibre_geoui_agent"
MODEL_NAME = (
    "openai-chat:gpt-5.2"  # Chat Completions explicitly; bare "openai:" flips to the Responses API in pydantic-ai 2
)
REASONING_EFFORT = "medium"
#: pydantic-ai ``retries``: tool / output validation failures handed back to the model before the run fails.
DEFAULT_RETRIES = 1

SYSTEM_PROMPT = inspect.cleandoc(
    """You are a map assistant. You control a geospatial visualisation application through three tools:

    - geo_ui_list_intent_extensions_tool: what the application supports. Call it at the start of a
      conversation. It returns the intent extensions the application attached (with their namespaced
      fields) and the layer catalogue (ids, titles, temporal coverage). A GeoIntent may only use those
      extensions and those layer ids; if the user names a product, pick the catalogue id that matches it.
    - geo_ui_get_state_tool: what is on screen now, as a GeoIntent. Call it before changing an existing
      view, because the user may have changed it by hand.
    - geo_ui_render_intent_tool: show a GeoIntent. It REPLACES the whole state: fields you leave out
      return to the application's defaults, so resend everything that must stay (layers, time,
      viewport, extension fields). Do not write `geoui_extensions`; the tool declares what the
      application supports. Fields of an unsupported extension and unknown layer ids are rejected with
      a message: read it, fix the intent and call the tool again once.

    GeoIntent conventions: `viewport.bbox` is [west, south, east, north] in degrees with
    `crs` "EPSG:4326"; `time.instant` is an ISO date (YYYY-MM-DD); `layers` is the stack bottom
    first, each {id, visible, opacity 0..1}; extension fields are namespaced keys such as
    `compare:layers` (on the root) or `raster-styling:min` (on a layer).

    Do exactly what the user asks, without dataset discovery or clarifying questions when the request
    names the layer, date and place. When you have rendered, answer with the structured result: one or
    two sentences describing what is now shown (layers, date, region, compare/styling if any). No URL:
    the view is already on screen.
    """
)

RESULT_DESCRIPTION = (
    "One or two sentences describing what is now shown: layers, date, region, and any compare or styling state."
)


class TextOutput(BaseModel):
    """Free-form text output. Used for conversational responses, clarifying
    questions, summaries, or any unstructured content."""

    content: str


class MaplibreAgentOutput(BaseModel):
    """Structured response from the MapLibre agent.

    Use this once the requested view has been rendered; use ``TextOutput``
    for clarification questions.
    """

    result: str = Field(..., description=RESULT_DESCRIPTION)


def validate_structured_output(output: Any) -> Any:
    """Output validator: a structured answer must carry a result."""
    if isinstance(output, TextOutput):
        return output
    if not str(getattr(output, "result", "")).strip():
        raise ModelRetry("Result is empty. Describe what is now shown.")
    return output


def maplibre_config(
    *, cdp_endpoint: str | None = None, app_url: str | None = None, environ: Mapping[str, str] | None = None
) -> BridgeConfig:
    """The bridge config: explicit arguments win over ``PLAYWRIGHT_CDP_ENDPOINT`` / ``GEOUI_APP_URL``."""
    base = config_from_env(environ)
    return BridgeConfig(cdp_endpoint=cdp_endpoint or base.cdp_endpoint, app_url=app_url or base.app_url)


def build_maplibre_agent(
    *,
    cdp_endpoint: str | None = None,
    app_url: str | None = None,
    extra_capabilities: Sequence[AbstractCapability] = (),
    environ: Mapping[str, str] | None = None,
    session_factory: SessionFactory | None = None,
    thinking: bool = True,
) -> Agent:
    """A ready-to-run MapLibre agent. Build a new one per Chromium attachment; ``session_factory`` injects a fake."""
    config = maplibre_config(cdp_endpoint=cdp_endpoint, app_url=app_url, environ=environ)
    capabilities: list[AbstractCapability] = [
        *([Thinking(effort=REASONING_EFFORT)] if thinking else []),
        *extra_capabilities,
    ]
    agent: Agent = Agent(
        MODEL_NAME,
        name=AGENT_NAME,
        system_prompt=(SYSTEM_PROMPT,),
        output_type=[MaplibreAgentOutput, TextOutput],
        toolsets=[make_geoui_toolset(config, session_factory=session_factory)],
        capabilities=capabilities,
        retries=DEFAULT_RETRIES,
    )
    agent.output_validator(validate_structured_output)
    return agent


__all__ = [
    "AGENT_NAME",
    "DEFAULT_RETRIES",
    "MODEL_NAME",
    "REASONING_EFFORT",
    "SYSTEM_PROMPT",
    "MaplibreAgentOutput",
    "TextOutput",
    "build_maplibre_agent",
    "maplibre_config",
    "validate_structured_output",
]


def run_smoke() -> None:
    import asyncio
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        print("Missing OPENAI_API_KEY. Create a .env from .env.example and populate it.")
        raise SystemExit(1)
    query = sys.argv[1] if len(sys.argv) > 1 else "Show MODIS Aqua aerosol optical depth over California on 2025-09-15."
    agent = build_maplibre_agent()
    result = asyncio.run(agent.run(query))
    print(result.output)
    print(result.usage)


if __name__ == "__main__":
    run_smoke()
