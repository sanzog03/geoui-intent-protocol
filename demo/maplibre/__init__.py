"""The MapLibre demo's Python half: the GeoUI MCP over CDP and its agent.

The React app itself is ``maplibre_geo_application/`` beside this package (Vite,
``npm run dev``); this package drives any page that exposes ``window.geoui``
(the ``@geoui/react`` SDK), the app included.

The three protocol tools (``geo_ui_list_intent_extensions_tool``,
``geo_ui_get_state_tool``, ``geo_ui_render_intent_tool``) are served over
MCP (``maplibre.mcp``) or as an in-process pydantic-ai toolset
(``maplibre.tools.pai``). Both reach the page through
:class:`maplibre.cdp.BridgeSession`, a Playwright connection to an
already-running Chromium's DevTools port. The extension catalogue and the
layer catalogue come from the page itself, so nothing here but the agent's
prompt is MapLibre-specific; ``maplibre.catalogue`` checks the page's catalogue against
the library's extension specs and pre-declares the supported URIs.
"""

from maplibre.catalogue import Catalogue, IntentExtension, LayerEntry, check_catalogue, prepare_intent
from maplibre.cdp import BridgeConfig, BridgeError, BridgeSession, GeoUISession, bridge, config_from_env

__all__ = [
    "BridgeConfig",
    "BridgeError",
    "BridgeSession",
    "Catalogue",
    "GeoUISession",
    "IntentExtension",
    "LayerEntry",
    "bridge",
    "check_catalogue",
    "config_from_env",
    "prepare_intent",
]
