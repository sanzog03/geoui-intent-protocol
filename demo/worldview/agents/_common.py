"""Plumbing shared by the two Worldview agents (GeoUI treatment, VLM baseline).

Both agents are bare :class:`pydantic_ai.Agent` instances assembled from an
:class:`AgentSpec`. They differ only in how they *observe and act* on
Worldview; everything else is held equal on purpose, because the benchmark
compares the interaction mechanism, not the discovery loop:

- the system prompt is a Claude Code skill (``worldview.plugin.load_skill``);
- discovery tools are the remote MCP servers from the plugin's ``.mcp.json``;
- the browser is the plugin's Playwright MCP attached to an external Chromium
  over CDP, narrowed per agent (``GEOUI_BROWSER_TOOLS`` / ``VLM_BROWSER_TOOLS``);
- the structured output (``result`` + ``url``) or a :class:`TextOutput`.

What the model sees (prompts, tool names and descriptions, output tool names,
capability ids) is pinned by ``demo/worldview/tests/agents/test_agent_surface.py``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.capabilities import MCP, AbstractCapability, Thinking
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.toolsets import AbstractToolset

from worldview.plugin import (
    MCPServer,
    load_mcp_config,
    playwright_server,
    plugin_dir,
    remote_capabilities,
    user_config_from_env,
)

MODEL_NAME = "openai-chat:gpt-5.2"  # Chat Completions explicitly; bare "openai:" flips to the Responses API in pydantic-ai 2
REASONING_EFFORT = "medium"
#: pydantic-ai ``retries``: how many times a tool / output validation failure
#: is handed back to the model as a retry prompt before the run fails.
DEFAULT_RETRIES = 1
#: The UI-driving baseline gets more: Playwright clicks on Worldview time out
#: now and then (overlays, tile loads) and each timeout is one retry. Applied
#: both as the agent's ``retries`` and as the Playwright server's
#: ``max_retries`` (MCP tools carry their own budget in pydantic-ai).
VLM_RETRIES = 3
#: Playwright MCP action timeout for the baseline (default 5000 ms is too
#: tight for Worldview's first-visit tour overlay and panel animations).
VLM_PLAYWRIGHT_ARGS: list[str] = ["--timeout-action", "15000"]
#: ``UsageLimits.request_limit`` the notebook passes to every run. This is
#: also pydantic-ai's default; it is stated explicitly so the cap is visible.
REQUEST_LIMIT = 50

RESULT_DESCRIPTION = (
    "Full sectioned response: INTENT, DATASET_OPTIONS, SELECTED_DATASET, WORLDVIEW_URL, "
    "PARAMETERS_USED, PROVENANCE, UNCERTAINTY, LIMITATIONS, MISSING_FIELDS, USER NARRATIVE, "
    "OPTIONAL ACTIONS, and the REQUIRED DISCLAIMER. Format is defined by the system prompt."
)


# -----------------------------------------------------------------------------
# Playwright MCP wiring (CDP-attach: external Chromium spans turns)
# -----------------------------------------------------------------------------
#
# The browser sits behind an MCP server speaking stdio. We need Chromium
# state (URL, pan/zoom, layer toggles) to survive across ``agent.run``
# calls so the user can interact with the map between turns. Earlier we
# tried pre-entering the stdio server in an async marimo cell so the
# subprocess would span every run — pydantic_ai's reference-counted
# ``MCPServer.__aenter__`` made that plausible on paper, but it doesn't
# survive marimo's task model: ``MCPServerStdio`` enters an ``anyio``
# task group internally, anyio insists the cancel scope exits on the
# same asyncio task that entered it, and marimo's per-cell tasks die
# the moment their cell returns. End result was
# ``RuntimeError: Attempted to exit cancel scope in a different task
# than it was entered in`` and the chat handler disappearing from the
# marimo function registry.
#
# Fix: don't try to persist the MCP at all. Keep Chromium alive
# *externally* (``demo/start.sh`` launches it with
# ``--remote-debugging-port``), create the Playwright MCP fresh per agent
# build, and have it attach via ``--cdp-endpoint``. The MCP's anyio scope
# is then fully contained in one run task; Chromium state lives outside
# Python entirely. Leaving ``cdp_endpoint=None`` falls back to vanilla
# per-run Chromium boot (no state persistence) — fine for headless tests,
# not the demo path.

# Playwright allow-lists. The GeoUI agent only ever opens a URL and reads
# the live one back; the VLM baseline needs the full observe-and-act
# surface. ``browser_navigate`` is the one-time landing for the VLM
# baseline; ``browser_evaluate`` is its end-of-turn URL read-back.
GEOUI_BROWSER_TOOLS: list[str] = ["browser_navigate", "browser_evaluate"]
GEOUI_BROWSER_DESCRIPTION = "Headed Chromium for opening Worldview URLs and reading back live state."

VLM_BROWSER_TOOLS: list[str] = [
    "browser_navigate",
    "browser_snapshot",
    "browser_take_screenshot",
    "browser_click",
    "browser_type",
    "browser_press_key",
    "browser_hover",
    "browser_drag",
    "browser_select_option",
    "browser_wait_for",
    "browser_evaluate",
]
VLM_BROWSER_DESCRIPTION = (
    "Headed Chromium for driving Worldview's UI directly via screenshot / snapshot / click / type."
)


def make_playwright_mcp(
    servers: Mapping[str, MCPServer],
    cdp_endpoint: str | None = None,
    *,
    extra_args: Sequence[str] = (),
    max_retries: int = DEFAULT_RETRIES,
) -> MCPServerStdio:
    """A fresh, unstarted Playwright MCP from the plugin config.

    ``cdp_endpoint`` (e.g. ``"http://localhost:9222"``) attaches it to the
    already-running Chromium so map state survives across turns; ``None``
    boots a private Chromium per run (first boot downloads ~150 MB).
    """
    return playwright_server(servers, cdp_endpoint, extra_args=extra_args, max_retries=max_retries)


def playwright_capability(server: MCPServerStdio, *, allowed_tools: list[str], description: str) -> MCP:
    """Wrap a caller-owned Playwright ``MCPServerStdio`` as a capability.

    ``native=False, local=server`` makes pydantic-ai use this exact server
    object, entered and exited inside each run (see the design note above).
    ``allowed_tools`` narrows the ~20-tool Playwright surface to what the
    agent's skill authorises.
    """
    return MCP(
        url="stdio://playwright-mcp",  # placeholder; only used for the capability id slug
        native=False,
        local=server,
        id="playwright_mcp",
        allowed_tools=allowed_tools,
        description=description,
    )


# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------


class TextOutput(BaseModel):
    """Free-form text output. Used for conversational responses, clarifying
    questions, summaries, or any unstructured content."""

    content: str


def validate_structured_output(output: Any) -> Any:
    """Output validator: a structured answer must carry a result and a URL."""
    if isinstance(output, TextOutput):
        return output
    if not str(getattr(output, "result", "")).strip():
        raise ModelRetry("Result is empty. Provide the structured Worldview-discovery response.")
    if not str(getattr(output, "url", "")).strip():
        raise ModelRetry("URL is empty. Provide a valid url")
    return output


# -----------------------------------------------------------------------------
# Agent assembly
# -----------------------------------------------------------------------------


@dataclass
class AgentSpec:
    """Everything that goes into one agent, kept inspectable for the surface
    golden and for the notebook (which adds a tracing hook)."""

    name: str
    system_prompts: list[str]
    toolsets: list[AbstractToolset]
    capabilities: list[AbstractCapability]
    output_cls: type[BaseModel]
    #: Remote MCP servers by config name, after secret substitution.
    servers: dict[str, MCPServer] = field(default_factory=dict)
    #: pydantic-ai ``retries`` (per-tool and output-validation retry budget).
    retries: int = DEFAULT_RETRIES


def load_servers(environ: Mapping[str, str] | None = None) -> dict[str, MCPServer]:
    """The plugin's MCP servers with ``${user_config.*}`` filled from ``environ``."""
    root = plugin_dir()
    return load_mcp_config(root, user_config=user_config_from_env(root, environ))


def standard_capabilities(
    servers: Mapping[str, MCPServer],
    *,
    cdp_endpoint: str | None,
    browser_tools: list[str],
    browser_description: str,
    playwright_args: Sequence[str] = (),
    playwright_max_retries: int = DEFAULT_RETRIES,
    extra: Sequence[AbstractCapability] = (),
) -> list[AbstractCapability]:
    """Remote discovery MCPs + narrowed Playwright + reasoning effort + extras."""
    return [
        *remote_capabilities(servers),
        playwright_capability(
            make_playwright_mcp(servers, cdp_endpoint, extra_args=playwright_args, max_retries=playwright_max_retries),
            allowed_tools=browser_tools,
            description=browser_description,
        ),
        Thinking(effort=REASONING_EFFORT),
        *extra,
    ]


def build_agent(spec: AgentSpec) -> Agent:
    """A bare pydantic-ai ``Agent`` from a spec. The output type is the
    structured class or :class:`TextOutput`, so the output tools are named
    ``final_result_<ClassName>`` and ``final_result_TextOutput``."""
    agent: Agent = Agent(
        MODEL_NAME,
        name=spec.name,
        system_prompt=tuple(spec.system_prompts),
        output_type=[spec.output_cls, TextOutput],
        toolsets=list(spec.toolsets),
        capabilities=list(spec.capabilities),
        retries=spec.retries,
    )
    agent.output_validator(validate_structured_output)
    return agent


# -----------------------------------------------------------------------------
# Wiring smoke test (shared ``__main__`` body)
# -----------------------------------------------------------------------------


def run_smoke(build: Callable[..., Agent], *, query: str) -> None:
    """One LLM round-trip to prove the agent wiring works.

    Requires ``OPENAI_API_KEY`` (from ``.env`` or the shell); MCP servers whose
    key is missing are skipped. The query is intentionally light; a clarifying
    ``TextOutput`` is a successful wiring test too.
    """
    from dotenv import load_dotenv

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        print("Missing OPENAI_API_KEY. Create a .env from .env.example and populate it.")
        raise SystemExit(1)

    async def _smoke() -> None:
        agent = build(cdp_endpoint=os.getenv("PLAYWRIGHT_CDP_ENDPOINT"))
        print("Running agent (wiring smoke test) ...\n")
        result = await agent.run(query)
        output = result.output
        print(f"Output type: {type(output).__name__}\n")
        print(output.model_dump_json(indent=2, exclude_none=True) if isinstance(output, BaseModel) else output)
        print(f"\nUsage: {result.usage()}")

    asyncio.run(_smoke())


__all__ = [
    "DEFAULT_RETRIES",
    "GEOUI_BROWSER_DESCRIPTION",
    "GEOUI_BROWSER_TOOLS",
    "MODEL_NAME",
    "REASONING_EFFORT",
    "REQUEST_LIMIT",
    "RESULT_DESCRIPTION",
    "VLM_BROWSER_DESCRIPTION",
    "VLM_BROWSER_TOOLS",
    "VLM_PLAYWRIGHT_ARGS",
    "VLM_RETRIES",
    "AgentSpec",
    "TextOutput",
    "build_agent",
    "load_servers",
    "make_playwright_mcp",
    "playwright_capability",
    "run_smoke",
    "standard_capabilities",
    "validate_structured_output",
]
