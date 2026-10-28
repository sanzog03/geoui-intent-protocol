"""The VLM baseline: the non-GeoUI ``mio-worldviewagent-v2`` skill plus full
Playwright browser control, on a bare pydantic-ai ``Agent``.

The skill knows nothing about the GeoUI protocol: it discovers layers with
the same remote MCPs and builds URLs with ``worldview_permalink_tool``. The
baseline adds a second system-prompt part, :data:`VLM_BROWSER_ADDENDUM`,
that tells the model to apply changes through Worldview's own UI with the
eleven Playwright tools (snapshot, screenshot, click, type, drag, ...) and to
read the final URL back from ``window.location.href``. This is the "drive
the app like a person would" baseline the poster compared the protocol
against.

Smoke test (one LLM call, needs ``.env``)::

    uv run python -m worldview.agents.vlm_agent
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability

from worldview.agents._common import (
    RESULT_DESCRIPTION,
    VLM_BROWSER_DESCRIPTION,
    VLM_BROWSER_TOOLS,
    VLM_PLAYWRIGHT_ARGS,
    VLM_RETRIES,
    AgentSpec,
    build_agent,
    load_servers,
    run_smoke,
    standard_capabilities,
)
from worldview.plugin import MIO_SKILL_DIR, Skill, load_skill, reference_toolset
from worldview.tools.pai import permalink_toolset

AGENT_NAME = "worldview_vlm_agent"
SKILL_NAME = "mio-worldviewagent-v2"

#: Second system-prompt part: how this baseline observes and acts on
#: Worldview. Lifted from the poster-era VLM prompt; the skill above carries
#: the discovery process, this carries the browser mechanics.
VLM_BROWSER_ADDENDUM = """# BROWSER INTERACTION (this deployment)

You drive the live NASA Worldview page through Playwright MCP tools. The
browser is your primary action and observation surface.

## Available browser tools
- Observation:
  - `browser_snapshot` — accessibility tree of the current page with element
    refs you can use to target subsequent actions. Cheapest accurate read of
    UI state.
  - `browser_take_screenshot` — PNG of the rendered page. Use when the
    accessibility tree isn't enough (e.g. you need to see the map itself, a
    chart, or a styled control with no accessible name).
- Action:
  - `browser_navigate(url)` — used **once** at the start of a session to open
    `https://worldview.earthdata.nasa.gov/`. Do not navigate to hand-built or
    tool-built Worldview URLs.
  - `browser_click(ref=...)` — click by accessibility ref.
  - `browser_type(ref=..., text=...)` — type into a text input.
  - `browser_press_key(key=...)` — keyboard input (Enter, ArrowLeft /
    ArrowRight for stepping the date, Escape).
  - `browser_hover(ref=...)` — reveal tooltips / hidden controls.
  - `browser_drag(startRef=..., endRef=...)` — pan the map or rearrange layers.
  - `browser_select_option` — dropdown choices (e.g. projection).
  - `browser_wait_for` — wait for tile loads / panels to open.
- URL read-back (end-of-turn only):
  - `browser_evaluate(function="() => window.location.href")` — call **once
    at the end of the turn**, after your UI manipulations are applied, to
    capture the final URL for the WORLDVIEW_URL output field. Do not use this
    tool to observe state; that is what `browser_snapshot` is for.

## Hard constraints
- **All visualization changes must flow through Worldview's UI controls** —
  clicks, typing, drags against the live page. `worldview_permalink_tool`
  may be used to *reason about* parameters, but the state of the
  visualization is whatever you produce by manipulating the UI; do not
  `browser_navigate` to a permalink after the initial landing-page navigation.
- **Once-per-turn observation budget.** Take at most **one** `browser_snapshot`
  at the start of the turn, and at most **one** `browser_take_screenshot` if
  the snapshot alone is insufficient. If you've already snapshotted and
  screenshotted once, do not snapshot again until you've performed an action
  that visibly changed the page (opened a panel, clicked a layer) and need to
  re-orient.
- **Turn-completion gate.** When your clicks / typing have applied the
  requested change and the page reflects it, the turn is **complete**. Do
  exactly one final `browser_evaluate(function="() => window.location.href")`
  to capture the URL for the output, then produce the final response. Do not
  snapshot or screenshot again "to verify"; Worldview's URL is allowed to lag
  a moment.

## Observe current Worldview state (refining turns only)
- Run this **at most once per turn, at the very start of a refining turn**
  (the user is iterating on an already-visualized state: "zoom to X",
  "change date to Y", "compare with Z"). The user may have panned, zoomed,
  toggled layers, or scrubbed the date directly in Worldview between turns;
  your only source of truth about the current state is what's on screen.
- Procedure (once, in order):
  1. `browser_snapshot` — read off active layers (left panel), current date
     (bottom bar), open dialogs, and any visible map labels indicating the
     centering / zoom.
  2. **Only if** the snapshot is insufficient, `browser_take_screenshot` once.
- On the **first turn** of a session there is nothing to observe: your first
  action is `browser_navigate("https://worldview.earthdata.nasa.gov/")`
  followed by an initial `browser_snapshot` so you can locate the controls.

## Apply changes via Worldview's UI
Use the accessibility-tree refs from your snapshot to target Worldview's
native controls:
- **Layer toggle**: find the layer row in the left-side layer panel; click its
  visibility toggle.
- **Add layer**: click **"+ Add Layers"** at the bottom of the layer panel; in
  the search box that opens, `browser_type` the exact layer label, then
  `browser_click` the matching result row.
- **Date change**: click the date label in the bottom-bar date selector,
  `browser_type` the new date in the form the input accepts (check the
  snapshot), then `browser_press_key(key="Enter")`. For one-day stepping use
  `browser_press_key(key="ArrowRight")` / `"ArrowLeft"` while the date is
  focused.
- **Pan**: `browser_drag` with start/end refs on the map canvas, choosing
  endpoints that displace the view in the desired direction.
- **Zoom**: click the **+** / **−** zoom buttons (top-left of the map), N
  times for N levels.
- **Compare mode**: click **"Compare"** in the top bar; configure A/B layers in
  the panel that opens.
- **Projection**: click the **"Projection"** dropdown in the top bar;
  `browser_select_option` to pick Arctic / Antarctic / Geographic.

If a click does nothing (page state unchanged), take one
`browser_take_screenshot` to re-orient — but do not loop snapshot/screenshot.
After at most one re-orientation, either succeed with a different control or
stop and report the obstacle in your response.

WORLDVIEW_URL in your final response is the URL captured by the single final
`browser_evaluate` call.
"""


def vlm_skill() -> Skill:
    """The vendored ``mio-worldviewagent-v2`` skill (no GeoUI, no browser text)."""
    return load_skill(MIO_SKILL_DIR)


class VLMAgentOutput(BaseModel):
    """Structured response from the VLM-baseline agent.

    Use this on the final turn, after the user has confirmed a dataset and
    the agent has applied UI changes; populate ``result`` with the full
    sectioned response and ``url`` with the URL read from
    ``window.location.href`` at the end of the turn. Use ``TextOutput`` for
    clarification questions or when no dataset has been confirmed yet.
    """

    result: str = Field(..., description=RESULT_DESCRIPTION)
    url: str = Field(
        ...,
        description="Worldview URL captured from window.location.href after the agent's UI manipulations were applied.",
    )


def vlm_spec(
    *,
    cdp_endpoint: str | None = None,
    extra_capabilities: Sequence[AbstractCapability] = (),
    environ: Mapping[str, str] | None = None,
) -> AgentSpec:
    """Assemble the baseline agent's parts (skill + browser addendum, toolsets, capabilities)."""
    skill = vlm_skill()
    servers = load_servers(environ)
    return AgentSpec(
        name=AGENT_NAME,
        system_prompts=[skill.body, VLM_BROWSER_ADDENDUM],
        toolsets=[permalink_toolset, reference_toolset(skill)],
        capabilities=standard_capabilities(
            servers,
            cdp_endpoint=cdp_endpoint,
            browser_tools=VLM_BROWSER_TOOLS,
            browser_description=VLM_BROWSER_DESCRIPTION,
            playwright_args=VLM_PLAYWRIGHT_ARGS,
            extra=extra_capabilities,
        ),
        output_cls=VLMAgentOutput,
        servers=servers,
        retries=VLM_RETRIES,
    )


def build_vlm_agent(
    *,
    cdp_endpoint: str | None = None,
    extra_capabilities: Sequence[AbstractCapability] = (),
    environ: Mapping[str, str] | None = None,
) -> Agent:
    """A ready-to-run VLM baseline agent. Build a new one per Chromium attachment."""
    return build_agent(vlm_spec(cdp_endpoint=cdp_endpoint, extra_capabilities=extra_capabilities, environ=environ))


__all__ = [
    "AGENT_NAME",
    "SKILL_NAME",
    "VLM_BROWSER_ADDENDUM",
    "VLMAgentOutput",
    "build_vlm_agent",
    "vlm_skill",
    "vlm_spec",
]


if __name__ == "__main__":
    run_smoke(build_vlm_agent, query="I'd like to see aerosol optical depth over California in mid September 2025.")
