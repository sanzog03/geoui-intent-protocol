"""GeoUI Intent Protocol.

An application-agnostic, typed, declarative description of a geospatial
visualization state (``GeoIntent``) that an agent reads and writes instead
of driving screenshots, DOM, or clicks. Adapters (``geoui.adapters``)
translate it to and from a concrete application; ``geoui.mcp`` serves the
two protocol tools over MCP; ``geoui.agents`` holds the IESO reference
agents and benchmark harness (optional extra).

Importing ``geoui`` pulls in only the protocol core and extensions.
"""

from geoui import extensions
from geoui.core import (
    GEOUI_PROTOCOL_VERSION,
    GeoIntent,
    LayerRef,
    TimeWindow,
    Viewport,
)

__version__ = "0.1.0"

__all__ = [
    "GEOUI_PROTOCOL_VERSION",
    "GeoIntent",
    "LayerRef",
    "TimeWindow",
    "Viewport",
    "__version__",
    "extensions",
]
