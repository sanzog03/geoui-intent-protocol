"""The GeoUI agent (treatment): the ``worldview-assistant`` Claude Code skill
run on a bare pydantic-ai ``Agent``.

The skill's ``SKILL.md`` is the system prompt verbatim. It prescribes the
GeoUI protocol tools for every visualisation change and allows exactly two
browser tools, ``browser_navigate`` (open the rendered URL) and
``browser_evaluate`` (read ``window.location.href`` back). No screenshots,
no clicks. The protocol tools and ``worldview_permalink_tool`` run
in-process (``worldview.tools.pai``); every other tool is a remote MCP from
the plugin's ``.mcp.json``.

Smoke test (one LLM call, needs ``.env``)::

    uv run python -m worldview.agents.geoui_agent
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability

from worldview.agents._common import (
    GEOUI_BROWSER_DESCRIPTION,
    GEOUI_BROWSER_TOOLS,
    RESULT_DESCRIPTION,
    AgentSpec,
    build_agent,
    load_servers,
    run_smoke,
    standard_capabilities,
)
from worldview.plugin import Skill, load_skill, plugin_dir, reference_toolset
from worldview.tools.pai import geoui_toolset, permalink_toolset

AGENT_NAME = "worldview_geoui_agent"
SKILL_NAME = "worldview-assistant"


def geoui_skill() -> Skill:
    """The ``worldview-assistant`` skill from the vendored plugin."""
    return load_skill(plugin_dir() / "skills" / SKILL_NAME)


class GeoUIAgentOutput(BaseModel):
    """Structured response from the GeoUI agent.

    Use this on the final turn, after the user has confirmed a dataset;
    populate ``result`` with the full sectioned response and ``url`` with
    the Worldview permalink returned by ``geo_ui_render_intent_tool``.
    Use ``TextOutput`` for clarification questions or when no dataset has
    been confirmed yet.
    """

    result: str = Field(..., description=RESULT_DESCRIPTION)
    url: str = Field(
        ...,
        description="Worldview permalink that resolves the science query, as returned by geo_ui_render_intent_tool.",
    )


def geoui_spec(
    *,
    cdp_endpoint: str | None = None,
    extra_capabilities: Sequence[AbstractCapability] = (),
    environ: Mapping[str, str] | None = None,
) -> AgentSpec:
    """Assemble the GeoUI agent's parts (prompt, toolsets, capabilities)."""
    skill = geoui_skill()
    servers = load_servers(environ)
    return AgentSpec(
        name=AGENT_NAME,
        system_prompts=[skill.body],
        toolsets=[geoui_toolset, permalink_toolset, reference_toolset(skill)],
        capabilities=standard_capabilities(
            servers,
            cdp_endpoint=cdp_endpoint,
            browser_tools=GEOUI_BROWSER_TOOLS,
            browser_description=GEOUI_BROWSER_DESCRIPTION,
            extra=extra_capabilities,
        ),
        output_cls=GeoUIAgentOutput,
        servers=servers,
    )


def build_geoui_agent(
    *,
    cdp_endpoint: str | None = None,
    extra_capabilities: Sequence[AbstractCapability] = (),
    environ: Mapping[str, str] | None = None,
) -> Agent:
    """A ready-to-run GeoUI agent. Build a new one per Chromium attachment."""
    return build_agent(geoui_spec(cdp_endpoint=cdp_endpoint, extra_capabilities=extra_capabilities, environ=environ))


__all__ = ["AGENT_NAME", "SKILL_NAME", "GeoUIAgentOutput", "build_geoui_agent", "geoui_skill", "geoui_spec"]


if __name__ == "__main__":
    run_smoke(build_geoui_agent, query="I'd like to see aerosol optical depth over California in mid September 2025.")
