"""GeoUI Intent Protocol.

An application-agnostic, typed, declarative description of a geospatial
visualization state (``GeoIntent``) that an agent reads and writes instead
of driving screenshots, DOM, or clicks. This package holds only the
protocol: the core models (``geoui.core``) and the versioned extensions
(``geoui.extensions``). It depends on pydantic alone.

Application adapters, the protocol tools, MCP serving and agents live
outside the library. The NASA Worldview reference implementation is the
``worldview`` package under ``demo/`` in this repository.
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
