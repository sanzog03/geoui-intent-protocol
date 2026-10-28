"""Worldview reference agents and benchmark harness, on bare pydantic-ai.

Two agents share the same discovery MCPs and differ only in the interaction
mechanism:

- :func:`build_geoui_agent` — the ``worldview-assistant`` Claude Code skill;
  drives Worldview through the GeoUI protocol tools and touches the browser
  only to open a URL and read it back (treatment).
- :func:`build_vlm_agent` — the non-GeoUI ``mio-worldviewagent-v2`` skill
  plus full Playwright browser control: screenshots, snapshots, clicks
  (baseline).

Both factories take ``cdp_endpoint`` (attach to the Chromium started by
``demo/start.sh``) and ``extra_capabilities`` (e.g. a tracing ``Hooks``).
Prompts come from the vendored skills, MCP servers from the plugin's
``.mcp.json`` (see ``worldview.plugin``).
"""

from worldview.agents._common import REQUEST_LIMIT, AgentSpec, TextOutput, build_agent
from worldview.agents.geoui_agent import GeoUIAgentOutput, build_geoui_agent, geoui_spec
from worldview.agents.vlm_agent import VLMAgentOutput, build_vlm_agent, vlm_spec

__all__ = [
    "REQUEST_LIMIT",
    "AgentSpec",
    "GeoUIAgentOutput",
    "TextOutput",
    "VLMAgentOutput",
    "build_agent",
    "build_geoui_agent",
    "build_vlm_agent",
    "geoui_spec",
    "vlm_spec",
]
