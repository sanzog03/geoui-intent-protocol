"""NASA Worldview bound to geouibench: two agents, one way of reading the state back.

The GeoUI agent (``worldview.agents.build_geoui_agent``) renders a GeoIntent
to a permalink and navigates to it; the VLM baseline
(``build_vlm_agent``) drives the live page and reads ``window.location.href``
back. Both end a turn with a Worldview URL, and :meth:`WorldviewApp.observe`
parses either into the same UI state, so the judge never knows which
mechanism produced it.

This file is the whole binding: ``python -m geouibench run benchmarks/worldview gold``
loads ``APP`` from here, ``prepare()`` brings up Chromium and warms the MCP
servers, and ``SYNTHETIC_STYLE`` is what ``geouibench synthetic`` hands to
deepeval. Datasets and results live beside it.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability

from geouibench import Budgets, SyntheticStyle
from geouibench.app import UIState
from worldview.adapter.mapping import url_to_intent
from worldview.adapter.permalink import BASE_LAYERS_SET, DEFAULT_REFERENCE_OVERLAYS
from worldview.agents import TextOutput, build_geoui_agent, build_vlm_agent
from worldview.plugin import plugin_dir

REPO_DIR = Path(__file__).resolve().parents[2]
CHROMIUM_SH = REPO_DIR / "demo" / "chromium.sh"

#: Per-turn budgets the efficiency metrics score against, identical for both
#: agents and for every golden that does not override them. Chosen as "one
#: minute and twenty thousand cache-adjusted tokens per assistant turn": a
#: turn within budget scores 1.0, a turn at twice the budget scores 0.5.
#: They are a fixed yardstick, not derived from either agent's results; the
#: cross-agent comparison is the summary's ratios.
DEFAULT_BUDGETS = Budgets(seconds_per_turn=60.0, tokens_per_turn=20_000)

#: What ``python -m geouibench synthetic benchmarks/worldview`` hands to ``deepeval generate``.
SYNTHETIC_STYLE = SyntheticStyle(
    scenario_context=(
        "A scientist asking a NASA Worldview assistant to visualise satellite imagery available in Worldview "
        "(GIBS layers such as MODIS and VIIRS corrected reflectance, MODIS aerosol optical depth, AIRS surface "
        "air temperature, GHRSST sea surface temperature anomalies, MOD13Q1 NDVI, Reference Labels and Features), "
        "on specific dates and regions, with refinements such as changing the date, panning to a place, comparing "
        "two dates, charting a time series or restyling a layer's colour scale"
    ),
    conversational_task=(
        "Produce the requested Worldview view and give the user a Worldview URL after each change, asking at most "
        "one clarifying question when the dataset is ambiguous"
    ),
    participant_roles="A domain scientist (user) and the Worldview assistant",
    scenario_format=(
        "Three to six sentences: who the user is, which layer(s), date(s) and region they want, and the two to four "
        "follow-up refinements they will ask for, in order"
    ),
    expected_outcome_format=(
        "Two sentences describing the final Worldview view the user should end up with: layers, date, region and any "
        "compare/chart/styling state"
    ),
    persona=(
        "A domain scientist who knows what they want to see, states layers, dates and regions precisely, "
        "asks for the refinements in the scenario one at a time, and stops once the final view is shown."
    ),
    max_user_simulations=4,
    max_goldens_per_context=2,
)

#: Tool names from the plugin's discovery servers (CMR, IESO validation, SDE).
#: prompts.md's verification rule: a fully specified prompt must not trigger these.
DISCOVERY_TOOLS: frozenset[str] = frozenset(
    {
        "search_collections",
        "get_collection_metadata",
        "get_granules",
        "search_worldview_layers",
        "validate_temporal_coverage",
        "sde_search_tool",
        "repository_search_tool",
        "umm_vis_lookup_tool",
        "earthdata_search_landing_page_tool",
    }
)

#: A Worldview URL inside free text. Layer modifiers use parentheses (``(opacity=1)``), so the
#: match runs to whitespace and :func:`_clean_url` trims markdown / punctuation afterwards.
WORLDVIEW_URL_RE = re.compile(r"https?://worldview\.earthdata\.nasa\.gov/\?\S+")


def _clean_url(url: str) -> str:
    url = url.rstrip(".,;:!?*`'\"<>]")
    while url.endswith(")") and url.count("(") < url.count(")"):  # a markdown link's closing paren
        url = url[:-1].rstrip(".,;:!?*`'\"")
    return url


CHATBOT_ROLES: dict[str, str] = {
    "geoui": (
        "A NASA Worldview assistant that turns a user's visualization request into a GeoIntent, "
        "renders it to a Worldview permalink with the GeoUI protocol tools and opens it in the browser."
    ),
    "vlm": (
        "A NASA Worldview assistant that fulfils a user's visualization request by operating "
        "Worldview's own user interface in the browser, reading the page and clicking its controls."
    ),
}


class WorldviewApp:
    """The :class:`geouibench.BenchmarkApp` implementation for NASA Worldview."""

    name = "worldview"
    agent_kinds = ("geoui", "vlm")  # geoui first: the reference the summary's ratios are relative to
    auto_layers: frozenset[str] = BASE_LAYERS_SET | frozenset(DEFAULT_REFERENCE_OVERLAYS)
    discovery_tools: frozenset[str] = DISCOVERY_TOOLS
    budgets: Budgets = DEFAULT_BUDGETS

    def prepare(self) -> dict[str, str]:
        """Before a run: the plugin must be present, Chromium up on CDP, the remote MCPs warm.

        Sources ``demo/chromium.sh`` (shared with ``demo/start.sh``) so the
        benchmark attaches to the same Chromium the notebook uses, and returns
        ``PLAYWRIGHT_CDP_ENDPOINT`` for the benchmark processes.
        """
        plugin_dir()  # raises with the submodule instructions when the plugin is missing
        script = f'source "{CHROMIUM_SH}" && ensure_chromium >&2 && printf "%s" "$PLAYWRIGHT_CDP_ENDPOINT"'
        endpoint = subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True).stdout.strip()
        if not endpoint:
            raise RuntimeError("demo/chromium.sh did not export PLAYWRIGHT_CDP_ENDPOINT")
        _warm_mcps()
        return {"PLAYWRIGHT_CDP_ENDPOINT": endpoint}

    def build_agent(
        self,
        kind: str,
        *,
        cdp_endpoint: str | None,
        extra_capabilities: Sequence[AbstractCapability],
    ) -> Agent[Any, Any]:
        if kind == "geoui":
            return build_geoui_agent(cdp_endpoint=cdp_endpoint, extra_capabilities=extra_capabilities)
        if kind == "vlm":
            return build_vlm_agent(cdp_endpoint=cdp_endpoint, extra_capabilities=extra_capabilities)
        raise ValueError(f"unknown agent kind {kind!r}; expected one of {self.agent_kinds}")

    def chatbot_role(self, kind: str) -> str:
        return CHATBOT_ROLES[kind]

    def output_url(self, output: Any) -> str | None:
        """The Worldview URL the assistant presented.

        Structured outputs carry it in ``url``. Either agent also sometimes
        answers as a text turn with the URL inline (both skills require a
        WORLDVIEW_URL in the reply); the last Worldview URL in the text counts,
        so a rendered view is not judged as "no state" because of the output form.
        """
        if output is None:
            return None
        url = getattr(output, "url", None)
        if isinstance(url, str) and url.strip():
            return url.strip()
        text = getattr(output, "content", None) if isinstance(output, TextOutput) else None
        if text is None and isinstance(output, str):
            text = output
        if not text:
            return None
        found = WORLDVIEW_URL_RE.findall(text)
        return _clean_url(found[-1]) if found else None

    def observe(self, url: str) -> UIState:
        """Parse a Worldview URL (permalink or live ``window.location.href``) and drop hidden layers."""
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.query:
            raise ValueError(f"not a Worldview URL: {url!r}")
        intent = url_to_intent(url)
        visible = [layer for layer in intent.layers if layer.visible]
        return intent.model_copy(update={"layers": visible})


def _warm_mcps() -> None:
    """Hit each remote MCP once so the first turn does not pay cold-start latency (never fatal)."""
    from worldview.agents.warm_mcps import warm

    try:
        results = asyncio.run(warm())
    except Exception as exc:  # noqa: BLE001 — a cold MCP slows the first turn; it does not invalidate the run
        print(f"MCP warm-up skipped: {exc}")
        return
    for r in results:
        print(f"  {r.url} -> {'HTTP ' + str(r.status) if r.ok else 'warm failed (' + str(r.error) + ')'}")


#: What ``geouibench`` loads from this directory.
APP = WorldviewApp()

__all__ = ["APP", "CHATBOT_ROLES", "DEFAULT_BUDGETS", "DISCOVERY_TOOLS", "SYNTHETIC_STYLE", "WorldviewApp"]
