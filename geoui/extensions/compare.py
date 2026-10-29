"""GeoUI Compare Extension — v1.0.0.

Adds A/B comparison (side-by-side or overlay) to a GeoIntent.

Declared by URI: ``https://geoui.org/ext/compare/v1.0.0``
Namespace prefix: ``compare:``

Required fields when used:
  - ``compare:layers`` — B-side layer stack.

Optional fields:
  - ``compare:active_side`` — "A" or "B" (default "A").
  - ``compare:time`` — TimeWindow for the B side (defaults to root time).
  - ``compare:mode`` — "swipe", "spy", or "opacity" (default "swipe").
  - ``compare:value`` — 0..100 swiper position / opacity (default 50).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from geoui.core import GeoIntent, LayerRef, TimeWindow
from geoui.extensions.spec import ExtensionSpec

URI = "https://geoui.org/ext/compare/v1.0.0"
PREFIX = "compare"

ActiveSide = Literal["A", "B"]
CompareMode = Literal["swipe", "spy", "opacity"]


class CompareFields(BaseModel):
    """Typed view of the ``compare:*`` fields on a GeoIntent."""

    layers: list[LayerRef] = Field(
        ..., min_length=1, description="The B-side layer stack (the A side is the root layers)."
    )
    active_side: ActiveSide = Field(default="A", description="Which side is active / in front.")
    time: TimeWindow | None = Field(default=None, description="Time for the B side; defaults to the root time.")
    mode: CompareMode = Field(default="swipe", description="swipe (split), spy (lens) or opacity (blend).")
    value: int = Field(default=50, ge=0, le=100, description="Swiper position or opacity, 0–100.")

    model_config = ConfigDict(populate_by_name=True)


def extract(intent: GeoIntent) -> CompareFields | None:
    """Pull ``compare:*`` fields off an intent.

    Returns None when no ``compare:*`` fields are present, whether or not
    the extension is declared (declaring it only says the document may use
    it). Raises ValueError if the document is malformed: fields present
    without the declaration, or present but incomplete.
    """
    declared = URI in intent.geoui_extensions
    raw = intent.extension_fields(PREFIX)

    if not raw:
        return None
    if not declared:
        raise ValueError(f"GeoIntent has `{PREFIX}:*` fields but does not declare {URI} in geoui_extensions")

    stripped = {k.removeprefix(f"{PREFIX}:"): v for k, v in raw.items()}
    return CompareFields(**stripped)


def inject(intent: GeoIntent, fields: CompareFields) -> GeoIntent:
    """Return a new GeoIntent with ``compare:*`` fields populated.

    Declares the extension URI if not already declared. Does not mutate.
    """
    extensions = list(intent.geoui_extensions)
    if URI not in extensions:
        extensions.append(URI)

    payload = fields.model_dump(exclude_none=True)
    extras = {f"{PREFIX}:{k}": v for k, v in payload.items()}

    base = intent.model_dump(by_alias=True)
    base["geoui_extensions"] = extensions
    base.update(extras)
    return GeoIntent.model_validate(base)


def validate(intent: GeoIntent) -> None:
    """Run compare-extension validation: raises ValueError if the document is malformed."""
    extract(intent)


SPEC = ExtensionSpec(
    uri=URI,
    prefix=PREFIX,
    scope="intent",
    fields=CompareFields,
    summary="Compare two layer stacks or two dates side by side (swipe, spy or opacity blend).",
)
