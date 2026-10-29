"""GeoUI Protocol extensions — v1.0.0.

Each extension defines:
  - `URI` — canonical, versioned URI identifying the extension.
  - `PREFIX` — the namespaced field prefix (`<prefix>:<field>`).
  - A typed Pydantic model for the extension's fields.
  - `extract(intent)` / `inject(intent, fields)` helpers that move data
    between the typed model and the GeoIntent's namespaced extra keys.
  - `validate(intent)` for layered validation; no-op when the extension
    is not used.
  - `SPEC` — an :class:`ExtensionSpec` describing it, so a consumer can
    advertise the extensions it supports (`ALL` lists the ones shipped here).

Declaring an extension's URI says a document *may* use it; the extension's
fields are validated only when some of them are present. Fields present
without the declaration are an error.
"""

from geoui.extensions import chart, compare, raster_styling
from geoui.extensions.spec import ExtensionSpec, declare, used_prefixes

#: Every extension shipped with the protocol, in a stable order.
ALL: tuple[ExtensionSpec, ...] = (compare.SPEC, chart.SPEC, raster_styling.SPEC)

__all__ = ["ALL", "ExtensionSpec", "chart", "compare", "declare", "raster_styling", "used_prefixes"]
