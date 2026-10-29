"""The MapLibre demo bound to geouibench: one agent, the state read from the page.

The demo (``demo/maplibre``) keeps nothing in the URL, so there is no URL to
observe. The agent (``maplibre.agents.build_maplibre_agent``) drives the
page through the CDP bridge, and after each turn :meth:`MaplibreApp.snapshot`
reads ``window.geoui.getState()`` through the same bridge and stores the
GeoIntent itself as the turn's handle (``geoui+json:<json>``), which
:meth:`MaplibreApp.observe` parses back at scoring time. The gold dataset is
the Worldview one without the chart scenarios (the demo does not attach the
chart extension) and with the opener for this app only.

``python -m geouibench run benchmarks/maplibre gold`` loads ``APP`` from here;
``prepare()`` brings up Chromium and checks the demo is being served at
``GEOUI_APP_URL`` (``npm run dev``).
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability

from geoui import GeoIntent
from geouibench import Budgets, SyntheticStyle
from geouibench.app import UIState
from maplibre import BridgeConfig, BridgeError, bridge
from maplibre.agents import build_maplibre_agent
from maplibre.tools import SessionFactory

REPO_DIR = Path(__file__).resolve().parents[2]
CHROMIUM_SH = REPO_DIR / "demo" / "chromium.sh"
DEFAULT_APP_URL = "http://127.0.0.1:5173"
#: The handle prefix: the turn's end state, serialised, so scoring needs no browser.
HANDLE_PREFIX = "geoui+json:"

#: The same yardstick as the Worldview benchmark, so runs compare.
DEFAULT_BUDGETS = Budgets(seconds_per_turn=60.0, tokens_per_turn=20_000)

SYNTHETIC_STYLE = SyntheticStyle(
    scenario_context=(
        "A scientist asking a map assistant to visualise NASA GIBS satellite imagery in a MapLibre map app "
        "(MODIS and VIIRS corrected reflectance, MODIS aerosol optical depth, AIRS surface air temperature, "
        "GHRSST sea surface temperature, land surface temperature, coastlines and reference layers), on specific "
        "dates and regions, with refinements such as changing the date, panning to a place, comparing two dates "
        "or two layers with a swipe, changing a layer's opacity or restyling its colour scale"
    ),
    conversational_task=(
        "Produce the requested map view and confirm what is shown after each change, asking at most one "
        "clarifying question when the layer is ambiguous"
    ),
    participant_roles="A domain scientist (user) and the map assistant",
    scenario_format=(
        "Three to six sentences: who the user is, which layer(s), date(s) and region they want, and the two to four "
        "follow-up refinements they will ask for, in order"
    ),
    expected_outcome_format=(
        "Two sentences describing the final map view the user should end up with: layers, date, region and any "
        "compare or styling state"
    ),
    persona=(
        "A domain scientist who knows what they want to see, states layers, dates and regions precisely, "
        "asks for the refinements in the scenario one at a time, and stops once the final view is shown."
    ),
    max_user_simulations=4,
    max_goldens_per_context=2,
)

CHATBOT_ROLES: dict[str, str] = {
    "geoui": (
        "A map assistant that turns a user's visualization request into a GeoIntent and renders it in a MapLibre "
        "map application with the GeoUI protocol tools, reading the application's layer catalogue first."
    ),
}


class MaplibreApp:
    """The :class:`geouibench.BenchmarkApp` implementation for the MapLibre demo."""

    name = "maplibre"
    agent_kinds = ("geoui",)
    auto_layers: frozenset[str] = frozenset()  # the app adds nothing by itself
    discovery_tools: frozenset[str] = frozenset()  # there is no discovery: the catalogue comes with the page
    budgets: Budgets = DEFAULT_BUDGETS
    #: Injected by tests; ``None`` means a real CDP bridge from the environment.
    session_factory: SessionFactory | None = None

    @staticmethod
    def app_url() -> str:
        return os.environ.get("GEOUI_APP_URL") or DEFAULT_APP_URL

    def prepare(self) -> dict[str, str]:
        """Before a run: Chromium up on CDP and the demo served at ``GEOUI_APP_URL``."""
        script = f'source "{CHROMIUM_SH}" && ensure_chromium >&2 && printf "%s" "$PLAYWRIGHT_CDP_ENDPOINT"'
        endpoint = subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True).stdout.strip()
        if not endpoint:
            raise RuntimeError("demo/chromium.sh did not export PLAYWRIGHT_CDP_ENDPOINT")
        url = self.app_url()
        try:
            httpx.get(url, timeout=5.0).raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"the MapLibre demo is not answering at {url} ({exc}); start it: npm run dev") from exc
        return {"PLAYWRIGHT_CDP_ENDPOINT": endpoint, "GEOUI_APP_URL": url}

    def build_agent(
        self,
        kind: str,
        *,
        cdp_endpoint: str | None,
        extra_capabilities: Sequence[AbstractCapability],
    ) -> Agent[Any, Any]:
        if kind != "geoui":
            raise ValueError(f"unknown agent kind {kind!r}; expected one of {self.agent_kinds}")
        return build_maplibre_agent(
            cdp_endpoint=cdp_endpoint,
            app_url=self.app_url(),
            extra_capabilities=extra_capabilities,
            session_factory=self.session_factory,
        )

    def chatbot_role(self, kind: str) -> str:
        return CHATBOT_ROLES[kind]

    def output_url(self, output: Any) -> str | None:
        """Never: the agent reports no handle; :meth:`snapshot` reads the state from the page instead."""
        return None

    async def snapshot(self, cdp_endpoint: str | None) -> str | None:
        """The page's state after the turn, as a ``geoui+json:`` handle; ``None`` when the page cannot be reached."""
        config = BridgeConfig(cdp_endpoint=cdp_endpoint or BridgeConfig().cdp_endpoint, app_url=self.app_url())
        opener = self.session_factory or (lambda: bridge(config))
        try:
            async with opener() as session:
                state = await session.get_state()
        except BridgeError:
            return None
        return HANDLE_PREFIX + json.dumps(state, separators=(",", ":"))

    def observe(self, url: str) -> UIState:
        """Parse a ``geoui+json:`` handle and drop hidden layers."""
        if not url.startswith(HANDLE_PREFIX):
            raise ValueError(f"not a {HANDLE_PREFIX} handle: {url[:40]!r}")
        intent = GeoIntent.model_validate_json(url[len(HANDLE_PREFIX) :])
        visible = [layer for layer in intent.layers if layer.visible]
        return intent.model_copy(update={"layers": visible})


#: What ``geouibench`` loads from this directory.
APP = MaplibreApp()

__all__ = ["APP", "CHATBOT_ROLES", "DEFAULT_BUDGETS", "HANDLE_PREFIX", "SYNTHETIC_STYLE", "MaplibreApp"]
