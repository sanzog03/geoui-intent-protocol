"""NASA Worldview bound to geobench: two agents, one way of reading the state back.

The GeoUI agent (``worldview.agents.build_geoui_agent``) renders a GeoIntent
to a permalink and navigates to it; the VLM baseline
(``build_vlm_agent``) drives the live page and reads ``window.location.href``
back. Both end a turn with a Worldview URL, and :meth:`WorldviewApp.observe`
parses either into the same UI state, so the judge never knows which
mechanism produced it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability

from geobench.app import UIState
from worldview.adapter.mapping import url_to_intent
from worldview.adapter.permalink import BASE_LAYERS_SET, DEFAULT_REFERENCE_OVERLAYS
from worldview.agents import TextOutput, build_geoui_agent, build_vlm_agent

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
    """The :class:`geobench.BenchmarkApp` implementation for NASA Worldview."""

    name = "worldview"
    agent_kinds = ("geoui", "vlm")
    auto_layers: frozenset[str] = BASE_LAYERS_SET | frozenset(DEFAULT_REFERENCE_OVERLAYS)
    discovery_tools: frozenset[str] = DISCOVERY_TOOLS

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


__all__ = ["CHATBOT_ROLES", "DISCOVERY_TOOLS", "WorldviewApp"]
