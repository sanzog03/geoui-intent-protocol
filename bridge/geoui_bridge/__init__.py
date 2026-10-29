"""GeoUI MCP over CDP: drive any page that exposes ``window.geoui`` (the ``@geoui/react`` SDK).

The three protocol tools (``geo_ui_list_intent_extensions_tool``,
``geo_ui_get_state_tool``, ``geo_ui_render_intent_tool``) are served over
MCP (``geoui_bridge.mcp``) or as an in-process pydantic-ai toolset
(``geoui_bridge.tools.pai``). Both reach the page through
:class:`geoui_bridge.cdp.BridgeSession`, a Playwright connection to an
already-running Chromium's DevTools port. The extension catalogue and the
layer catalogue come from the page itself, so this package knows no
application; ``geoui_bridge.catalogue`` checks the page's catalogue against
the library's extension specs and pre-declares the supported URIs.
"""

from geoui_bridge.catalogue import Catalogue, IntentExtension, LayerEntry, check_catalogue, prepare_intent
from geoui_bridge.cdp import BridgeConfig, BridgeError, BridgeSession, GeoUISession, bridge, config_from_env

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
