"""A self-describing record of one extension, for consumers that advertise what they support.

An application (or the tool layer in front of it) lists the
:class:`ExtensionSpec` objects it implements. From that list it can tell an
agent which extensions exist and what their fields are (``describe``),
pre-declare their URIs on incoming documents, and refuse namespaces it does
not implement (``used_prefixes``). The producer-side rule of the protocol,
"declare what you use", is then satisfied by the consumer that knows what it
accepts, instead of by every producer remembering the URI strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from geoui.core import GeoIntent

Scope = Literal["intent", "layer"]


@dataclass(frozen=True)
class ExtensionSpec:
    """What an extension is: its URI, key prefix, where its fields live, and their typed model."""

    uri: str
    prefix: str
    scope: Scope
    fields: type[BaseModel]
    summary: str

    @property
    def name(self) -> str:
        return self.prefix

    def keys(self) -> list[str]:
        """The namespaced keys a producer writes, e.g. ``compare:layers``."""
        return [f"{self.prefix}:{field}" for field in self.fields.model_fields]

    def describe(self) -> dict[str, Any]:
        """A plain dict an agent can read: name, uri, scope, summary, keys and the fields' JSON schema."""
        schema = self.fields.model_json_schema()
        return {
            "name": self.prefix,
            "uri": self.uri,
            "scope": self.scope,
            "summary": self.summary,
            "keys": self.keys(),
            "required": [f"{self.prefix}:{field}" for field in schema.get("required", [])],
            "fields_schema": schema,
        }


def used_prefixes(intent: GeoIntent) -> set[str]:
    """Every namespace prefix with at least one ``<prefix>:<field>`` key on the intent or on any layer."""
    found: set[str] = set()
    for key in intent.__pydantic_extra__ or {}:
        if ":" in key:
            found.add(key.split(":", 1)[0])
    for layer in intent.layers:
        for key in layer.__pydantic_extra__ or {}:
            if ":" in key:
                found.add(key.split(":", 1)[0])
    return found


def declare(intent: GeoIntent, uris: list[str] | tuple[str, ...]) -> GeoIntent:
    """Return a copy of ``intent`` that also declares ``uris`` (order kept, duplicates dropped). Does not mutate."""
    merged = list(intent.geoui_extensions)
    for uri in uris:
        if uri not in merged:
            merged.append(uri)
    if merged == list(intent.geoui_extensions):
        return intent
    base = intent.model_dump(by_alias=True)
    base["geoui_extensions"] = merged
    return GeoIntent.model_validate(base)


__all__ = ["ExtensionSpec", "Scope", "declare", "used_prefixes"]
