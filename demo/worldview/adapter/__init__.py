"""Reference GeoUI adapter: NASA Worldview.

Translates ``GeoIntent`` to and from Worldview permalink URLs. The
application itself is never modified; the adapter only maps protocol
fields onto Worldview's existing permalink grammar.
"""

from worldview.adapter.mapping import (
    CRS_TO_WORLDVIEW_PROJECTION,
    WORLDVIEW_PROJECTION_TO_CRS,
    intent_to_permalink_input,
    intent_to_url,
    permalink_input_to_intent,
    url_to_intent,
)
from worldview.adapter.permalink import (
    BASE_LAYERS,
    DEFAULT_BASE_URL,
    LayerSpec,
    WorldviewPermalinkInputSchema,
    build_url,
)
from worldview.adapter.url_parser import parse_url

__all__ = [
    "BASE_LAYERS",
    "CRS_TO_WORLDVIEW_PROJECTION",
    "DEFAULT_BASE_URL",
    "WORLDVIEW_PROJECTION_TO_CRS",
    "LayerSpec",
    "WorldviewPermalinkInputSchema",
    "build_url",
    "intent_to_permalink_input",
    "intent_to_url",
    "parse_url",
    "permalink_input_to_intent",
    "url_to_intent",
]
