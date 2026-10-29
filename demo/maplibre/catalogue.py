"""The page's catalogue, checked against the library, and the pre-declaration of its extensions.

``window.geoui.describe()`` tells the bridge which extensions the app attached
(as ``ExtensionSpec.describe()`` documents, embedded in the SDK from
``schemas/``) and which layers it can show. :func:`check_catalogue` refuses a
catalogue whose extensions this library does not know or whose documents have
drifted from the library's, so the typed validators below apply to exactly
what the page implements. :func:`prepare_intent` is the consumer-side rule of
the protocol: declare the supported URIs on the incoming intent, reject
namespaces the page did not attach, and run the library's validators.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from geoui.core import GeoIntent
from geoui.extensions import ALL, ExtensionSpec, chart, compare, declare, raster_styling, used_prefixes
from maplibre.cdp import BridgeError

DEFAULT_CRS = "EPSG:4326"


class IntentExtension(BaseModel):
    """One supported extension, as ``ExtensionSpec.describe()`` lays it out."""

    name: str = Field(description="The namespace prefix, e.g. compare.")
    uri: str = Field(description="The extension's canonical, versioned URI.")
    scope: str = Field(description='"intent": keys on the GeoIntent root; "layer": keys on each LayerRef.')
    summary: str = Field(description="When to use it, in one line.")
    keys: list[str] = Field(description="The namespaced keys, e.g. compare:layers.")
    required: list[str] = Field(description="Keys that must be present once the extension is used.")
    fields_schema: dict[str, Any] = Field(description="JSON schema of the fields (without the prefix).")


class LayerTime(BaseModel):
    start: str = Field(description="First available date (ISO).")
    end: str | None = Field(default=None, description="Last available date, or null when ongoing.")
    period: str | None = Field(default=None, description="ISO 8601 duration between steps, e.g. P1D.")


class LayerEntry(BaseModel):
    """One layer the application can show; ``id`` is what a GeoIntent's ``layers[].id`` must use."""

    id: str = Field(description="Layer id as the application resolves it.")
    title: str = Field(description="Human-readable name.")
    time: LayerTime | None = Field(default=None, description="Temporal coverage, when the layer is time-varying.")


class Catalogue(BaseModel):
    """What ``window.geoui.describe()`` returns."""

    model_config = ConfigDict(extra="ignore")

    version: str = Field(description="SDK version in the page.")
    protocol: str = Field(description="GeoUI protocol version the page speaks.")
    extensions: list[IntentExtension] = Field(default_factory=list)
    layers: list[LayerEntry] = Field(default_factory=list)

    @property
    def extension_names(self) -> list[str]:
        return [ext.name for ext in self.extensions]

    @property
    def extension_uris(self) -> list[str]:
        return [ext.uri for ext in self.extensions]


#: The extensions this library version can validate, by URI.
KNOWN_SPECS: dict[str, ExtensionSpec] = {spec.uri: spec for spec in ALL}
#: Typed validation of an extension's fields on a declared intent (raises ``ValueError``).
VALIDATORS: dict[str, Callable[[GeoIntent], None]] = {
    compare.URI: compare.validate,
    chart.URI: chart.validate,
    raster_styling.URI: raster_styling.validate,
}


def check_catalogue(catalogue: Catalogue) -> None:
    """Every extension the page attached must be one this library knows, with the same document."""
    for ext in catalogue.extensions:
        spec = KNOWN_SPECS.get(ext.uri)
        if spec is None:
            raise BridgeError(
                f"the page attached extension {ext.name!r} ({ext.uri}) which this geoui-protocol version does not know; "
                f"known: {', '.join(KNOWN_SPECS)}"
            )
        expected = spec.describe()
        got = ext.model_dump()
        if got != expected:
            drifted = sorted(key for key in expected if got.get(key) != expected[key])
            raise BridgeError(
                f"the page's document for extension {ext.name!r} differs from the library's in {drifted}; "
                "regenerate the SDK types (npm run gen:types) or update geoui-protocol"
            )


def _layer_ids_referenced(intent: GeoIntent) -> list[str]:
    ids = [layer.id for layer in intent.layers]
    for key, value in (intent.__pydantic_extra__ or {}).items():
        if key.endswith(":layers") and isinstance(value, list):
            ids.extend(str(item["id"]) for item in value if isinstance(item, dict) and "id" in item)
            ids.extend(item.id for item in value if hasattr(item, "id"))
    return ids


def prepare_intent(intent: GeoIntent, catalogue: Catalogue) -> GeoIntent:
    """The document the page receives: supported URIs declared, everything else refused with a message the agent can act on.

    Raises ``ValueError`` for an extension the page did not attach, a CRS other
    than EPSG:4326, a layer id outside the page's catalogue (when it publishes
    one), and incomplete or ill-typed extension fields.
    """
    names = catalogue.extension_names
    unsupported = sorted(used_prefixes(intent) - set(names))
    if unsupported:
        raise ValueError(
            f"extension(s) {unsupported} are not available in this app; "
            f"supported: {', '.join(names)} (see geo_ui_list_intent_extensions_tool)"
        )
    if intent.viewport.crs != DEFAULT_CRS:
        raise ValueError(f"viewport.crs {intent.viewport.crs!r} is not supported by this app; use {DEFAULT_CRS}")
    if catalogue.layers:
        known = [layer.id for layer in catalogue.layers]
        unknown = list(dict.fromkeys(i for i in _layer_ids_referenced(intent) if i not in known))
        if unknown:
            shown = ", ".join(known[:20]) + (", ..." if len(known) > 20 else "")
            raise ValueError(
                f"unknown layer id(s) {unknown}; known ids: {shown} (see geo_ui_list_intent_extensions_tool)"
            )
    declared = declare(intent, catalogue.extension_uris)
    for uri in catalogue.extension_uris:
        validator = VALIDATORS.get(uri)
        if validator is not None:
            validator(declared)
    return declared


__all__ = [
    "DEFAULT_CRS",
    "KNOWN_SPECS",
    "VALIDATORS",
    "Catalogue",
    "IntentExtension",
    "LayerEntry",
    "LayerTime",
    "check_catalogue",
    "prepare_intent",
]
