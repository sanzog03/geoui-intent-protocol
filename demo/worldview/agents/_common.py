"""Plumbing shared by the IESO Worldview agents (GeoUI treatment, VLM baseline).

The two agents differ only in how they *observe and act* on Worldview:
the GeoUI variant emits ``GeoIntent`` through two protocol tools and opens
the resulting URL; the VLM baseline drives Worldview's UI through
Playwright screenshots, snapshots and clicks. Everything else is held
equal on purpose, because the benchmark compares the interaction
mechanism, not the discovery loop:

- the two remote MCPs (CMR, IESO validation) — :func:`get_default_ieso_worldview_capabilities`
- the three local discovery tools — :func:`discovery_tools`
- the Playwright-over-CDP wiring — :func:`make_playwright_mcp`, :func:`playwright_capability`
- the input schema, the structured-output check and the smoke runner

What stays in each agent module is everything the model can see or that
the benchmark logs record: the system prompt, the config ``description``,
the output-schema class (its name becomes the pydantic-ai output tool
name) and the agent class (its name becomes ``agent.name``). See
``demo/worldview/tests/agents/test_agent_surface.py``.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from akd._base import InputSchema, OutputSchema, TextOutput
from akd.tools import BaseTool
from akd_ext.agents._base import PydanticAIBaseAgent
from akd_ext.tools.sde_search import SDESearchTool
from akd_ext.tools.worldview import EarthdataSearchLandingPageTool, UMMVisLookupTool
from pydantic import Field
from pydantic_ai.capabilities import MCP
from pydantic_ai.mcp import MCPServerStdio, MCPServerStreamableHTTP

# Init timeout for remote streamable-HTTP MCPs (CMR, IESO Validation).
# The default ``MCPServerStreamableHTTP.timeout`` is 5 s, which is too
# tight for FastMCP-hosted instances that hibernate when idle; their
# wake-up can take 10–25 s. We've seen ``mcp.py:748`` fire its
# ``anyio.fail_after`` on the first ``arun`` after a quiet period.
# 30 s leaves comfortable headroom without masking real hangs.
_REMOTE_MCP_INIT_TIMEOUT_S = 30.0


# -----------------------------------------------------------------------------
# Remote MCP capabilities (identical for both agents)
# -----------------------------------------------------------------------------


def get_default_ieso_worldview_capabilities() -> list[Any]:
    """Default remote MCP capabilities, shared by both agents.

    Same as :func:`akd_ext.agents.ieso_worldview.get_default_ieso_worldview_capabilities`
    minus the ``worldview_permalink_tool`` MCP (the GeoUI variant replaces
    it with the local ``geoui_render_intent`` tool; the VLM baseline drives
    the UI instead) and minus the three IESO/SDE MCPs whose tools we now run
    locally to sidestep FastMCP Cloud cold-start DNS hiccups:

      - ``umm_vis_lookup_tool``               → ``UMMVisLookupTool`` (local)
      - ``earthdata_search_landing_page_tool``→ ``EarthdataSearchLandingPageTool`` (local)
      - ``sde_search_tool``                   → ``SDESearchTool`` (local)

    The two MCPs that remain have no local equivalent in this codebase:

      - ``CMR_MCP_Server`` (AWS-hosted; no cold-start risk).
      - ``IESO_Validation_MCP_Server`` (FastMCP-hosted; may cold-start —
        we accept that until a local version exists).

    The discovery surface is held equal between the two agents on
    purpose — the comparison the poster makes is about observation /
    action cost, not metadata-lookup cost.

    Auth tokens are read from env at construction time:
      - VECTOR_DB_TOOL_KEY:  IESO validation / layer vector-DB server
      - IESO_MCP_KEY, SDE_MCP_KEY: currently unused; were for the disabled MCPs

    Why each ``MCP(...)`` wraps a pre-built ``MCPServerStreamableHTTP``:
        Passing ``timeout=...`` straight to ``MCP(url=...)`` is not
        supported — the ``MCP`` capability hardcodes the default
        ``MCPServerStreamableHTTP`` timeout (5 s). Building the server
        explicitly and handing it to ``local=`` lets us set
        ``_REMOTE_MCP_INIT_TIMEOUT_S`` so FastMCP cold-starts don't
        fire ``mcp.py:748``'s ``anyio.fail_after`` on the first turn.
        ``builtin=False`` forces pydantic_ai to use our local server
        rather than negotiating an in-model builtin MCP path.
    """
    # CMR MCP — AWS Lambda-hosted; trailing slash is load-bearing
    # (server returns 307 redirect without it, and pydantic_ai's
    # streamable-HTTP client raises on raise_for_status rather than
    # following the redirect).
    cmr_server = MCPServerStreamableHTTP(
        "https://w4hu71445m.execute-api.us-east-1.amazonaws.com/mcp/cmr/mcp/",
        timeout=_REMOTE_MCP_INIT_TIMEOUT_S,
    )

    # IESO Validation MCP — FastMCP free instance that hibernates;
    # this is the cold-start culprit. Auth header is built here so we
    # can also pass it to the underlying server (the ``MCP`` capability
    # only forwards ``authorization_token`` to its builtin path, not to
    # our pre-built ``local=`` server).
    vector_db_token = os.environ.get("VECTOR_DB_TOOL_KEY")
    ieso_validation_server = MCPServerStreamableHTTP(
        "https://ieso-benchmark-mcp-tools.fastmcp.app/mcp",
        headers={"Authorization": f"Bearer {vector_db_token}"} if vector_db_token else None,
        timeout=_REMOTE_MCP_INIT_TIMEOUT_S,
    )

    return [
        # ── DISABLED: replaced by local UMMVisLookupTool ──────────────────
        # MCP(
        #     url="https://sudden-gold-carp-features-tool-cmr-uat.fastmcp.app/mcp",
        #     id="ieso-worldview-tool-umm_vis_lookup_tool",
        #     allowed_tools=["umm_vis_lookup_tool"],
        #     authorization_token=f"Bearer {os.environ.get('IESO_MCP_KEY')}",
        #     description="Layerid Visualization lookup for CMR Concept id",
        # ),
        # ── DISABLED: replaced by local EarthdataSearchLandingPageTool ────
        # MCP(
        #     url="https://sudden-gold-carp-features-tools-earthdata-search-da3be0.fastmcp.app/mcp",
        #     id="ieso-worldview-tool-earthdata_search_landing_page_tool",
        #     allowed_tools=["earthdata_search_landing_page_tool"],
        #     authorization_token=f"Bearer {os.environ.get('IESO_MCP_KEY')}",
        #     description="Earthdata search landing page for concept id",
        # ),
        MCP(
            url="https://w4hu71445m.execute-api.us-east-1.amazonaws.com/mcp/cmr/mcp/",
            local=cmr_server,
            builtin=False,  # Force local streamable-HTTP client (respects trailing slash)
            id="CMR_MCP_Server",
            allowed_tools=[
                "search_collections",
                "get_granules",
                "get_collection_metadata",
            ],
            description="CMR MCP server to fetch metadata information including links to download datasets",
        ),
        # ── Currently authorization issue ────
        MCP(
            url="https://ieso-benchmark-mcp-tools.fastmcp.app/mcp",
            local=ieso_validation_server,
            builtin=False,
            id="IESO_Validation_MCP_Server",
            authorization_token=f"Bearer {vector_db_token}" if vector_db_token else None,
            allowed_tools=[
                "search_worldview_layers",
                "validate_temporal_coverage",
            ],
        ),
        # ── DISABLED: replaced by local SDESearchTool ─────────────────────
        # MCP(
        #     url="https://brainy-lime-pheasant.fastmcp.app/mcp",
        #     id="sde_mcp_tool",
        #     allowed_tools=["sde_search_tool"],
        #     authorization_token=f"Bearer {os.environ.get('SDE_MCP_KEY')}",
        # ),
    ]


def discovery_tools() -> list[BaseTool]:
    """The three local discovery tools both agents share.

    They previously ran behind FastMCP-hosted servers; the local versions
    are functionally equivalent and avoid the cold-start DNS issue (see
    :func:`get_default_ieso_worldview_capabilities`).
    """
    return [
        UMMVisLookupTool(),
        EarthdataSearchLandingPageTool(),
        SDESearchTool(),
    ]


# -----------------------------------------------------------------------------
# Playwright MCP wiring (CDP-attach: external Chromium spans turns)
# -----------------------------------------------------------------------------
#
# The browser sits behind an MCP server speaking stdio. We need Chromium
# state (URL, pan/zoom, layer toggles) to survive across ``agent.arun``
# calls so the user can interact with the map between turns. Earlier we
# tried pre-entering the stdio server in an async marimo cell so the
# subprocess would span every arun — pydantic_ai's reference-counted
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
# *externally* (the user launches it with ``--remote-debugging-port``),
# create the Playwright MCP fresh per arun, and have it attach via
# ``--cdp-endpoint``. The MCP's anyio scope is then fully contained in
# one arun task; Chromium state lives outside Python entirely.
#
# Usage from the notebook (``demo/chat.py``):
#
#     pw = make_playwright_mcp(cdp_endpoint="http://localhost:9222")
#     agent = IESOWorldviewGeoUIAgent(
#         IESOWorldviewGeoUIAgentConfig(
#             capabilities=[
#                 *get_default_ieso_worldview_capabilities(),
#                 geoui_agent.playwright_capability(pw),
#             ],
#         ),
#     )
#
# Before opening the notebook the user launches Chromium with remote
# debugging enabled (``demo/start.sh`` does this), for example:
#
#     /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
#         --remote-debugging-port=9222 \
#         --user-data-dir=/tmp/worldview-chromium
#
# Leaving ``cdp_endpoint=None`` falls back to vanilla per-turn
# Chromium boot (no state persistence) — useful for headless tests but
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


def make_playwright_mcp(cdp_endpoint: str | None = None) -> MCPServerStdio:
    """Return an unstarted Playwright MCP stdio server.

    Args:
        cdp_endpoint: If set, the MCP attaches to an already-running
            Chromium via Chrome DevTools Protocol (e.g.
            ``"http://localhost:9222"``). Required for state to survive
            across turns. If ``None``, the MCP boots its own Chromium
            on each arun (first such boot downloads ~150 MB).

    Used by:
        ``demo/chat.py`` ``_agent`` cell, which reads
        ``PLAYWRIGHT_CDP_ENDPOINT`` from the env and passes it through
        so the long-lived Chromium launched by ``demo/start.sh``
        persists across chat turns. The launcher is agent-agnostic;
        both agents attach to the same CDP endpoint.

    Why ``cdp_endpoint`` is optional:
        The same helper serves two flows. The demo / notebook path
        sets ``cdp_endpoint`` so Chromium state (URL, pan/zoom, layer
        toggles) lives outside Python and survives across the
        per-arun MCP lifecycle. The fresh-browser-per-arun path
        (``cdp_endpoint=None``) is useful for headless tests where
        state persistence doesn't matter.

    Why ``timeout=30``:
        ``MCPServerStdio``'s default init timeout is 5 s, which is
        too tight for ``npx @playwright/mcp@latest`` on a cold
        node_modules cache plus a fresh Chromium-CDP handshake.
        We've seen ``anyio.fail_after`` fire at
        ``pydantic_ai/mcp.py:748`` on the first turn of a session.
        30 s leaves headroom without masking real hangs.
    """
    args = ["@playwright/mcp@latest"]
    if cdp_endpoint:
        args += ["--cdp-endpoint", cdp_endpoint]
    return MCPServerStdio(command="npx", args=args, timeout=30)


def playwright_capability(server: MCPServerStdio, *, allowed_tools: list[str], description: str) -> MCP:
    """Wrap an externally-owned ``MCPServerStdio`` as a pydantic_ai capability.

    ``builtin=False`` forces the local toolset path; ``local=server`` reuses
    the caller's already-instantiated MCP server instead of building a
    fresh one. ``allowed_tools`` restricts the ~20-tool Playwright surface
    to what the agent should reach for; each agent module passes its own
    list (``GEOUI_BROWSER_TOOLS`` / ``VLM_BROWSER_TOOLS``) so the model
    doesn't wander into flows its system prompt doesn't authorize.

    Why ``builtin=False, local=server``:
        The caller owns the ``MCPServerStdio`` lifetime, and each
        ``agent.arun`` enters and exits the MCP inside one anyio
        task. An earlier attempt that pre-entered the MCP in a marimo
        cell and held it across turns raised
        ``RuntimeError: Attempted to exit cancel scope in a different
        task than it was entered in`` — anyio binds the MCP's internal
        task group to the entering task and marimo's per-cell tasks
        die on return. The current design avoids that by launching
        Chromium externally (see ``demo/start.sh``) and
        letting the MCP live one arun at a time; this capability
        wrapper is the API that supports that pattern.
    """
    return MCP(
        url="stdio://playwright-mcp",  # placeholder; only used for the cap's id slug
        builtin=False,
        local=server,
        id="playwright_mcp",
        allowed_tools=allowed_tools,
        description=description,
    )


# -----------------------------------------------------------------------------
# Shared schema and agent base
# -----------------------------------------------------------------------------


class IESOWorldviewAgentInputSchema(InputSchema):
    """Input schema shared by both IESO Worldview agents."""

    query: str = Field(..., description="Earth science query to interact with worldview visualization")


class IESOWorldviewAgentBase[InputT: InputSchema, OutputT: OutputSchema](PydanticAIBaseAgent[InputT, OutputT]):
    """Base for the two IESO Worldview agents.

    Subclasses set ``input_schema``, ``output_schema`` (their structured
    schema ``| TextOutput``) and ``config_schema``. The class *name* of the
    subclass is model-visible (``agent.name`` and the pydantic-ai output
    tool name derive from it), so keep the concrete classes in their own
    modules.
    """

    def check_output(self, output) -> str | None:
        # Structured outputs (``result`` + ``url``); ``TextOutput`` passes through.
        if isinstance(output, OutputSchema) and not isinstance(output, TextOutput):
            if not output.result.strip():
                return "Result is empty. Provide the structured Worldview-discovery response."
            if not output.url.strip():
                return "URL is empty. Provide a valid url"
        return super().check_output(output)


# -----------------------------------------------------------------------------
# Wiring smoke test (shared ``__main__`` body)
# -----------------------------------------------------------------------------


def run_smoke(agent_cls: type[PydanticAIBaseAgent], *, query: str) -> None:
    """One LLM round-trip to prove the agent wiring works.

    Requires ``OPENAI_API_KEY`` and ``VECTOR_DB_TOOL_KEY`` (from ``.env`` or
    the shell). The query is intentionally light; the agent may respond with
    a clarifying ``TextOutput`` rather than a rendered URL — that's a
    successful wiring test either way.
    """
    from dotenv import load_dotenv

    load_dotenv()

    required = ["OPENAI_API_KEY", "VECTOR_DB_TOOL_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"Missing env vars: {missing}")
        print("Create a .env from .env.example and populate the required keys.")
        raise SystemExit(1)

    async def _smoke() -> None:
        agent = agent_cls()
        params = agent.input_schema(query=query)
        print("Running agent (wiring smoke test) ...\n")
        output = await agent.arun(params)
        print(f"Output type: {type(output).__name__}\n")
        if hasattr(output, "model_dump_json"):
            print(output.model_dump_json(indent=2, exclude_none=True))
        else:
            print(output)
        ctx = agent.last_run_context
        if ctx and ctx.usage is not None:
            print(f"\nUsage: {ctx.usage}")

    asyncio.run(_smoke())


__all__ = [
    "GEOUI_BROWSER_DESCRIPTION",
    "GEOUI_BROWSER_TOOLS",
    "VLM_BROWSER_DESCRIPTION",
    "VLM_BROWSER_TOOLS",
    "IESOWorldviewAgentBase",
    "IESOWorldviewAgentInputSchema",
    "discovery_tools",
    "get_default_ieso_worldview_capabilities",
    "make_playwright_mcp",
    "playwright_capability",
    "run_smoke",
]
