"""GeoUI Chart Extension — v1.0.0.

Adds time-series statistical charting over an area-of-interest.

Declared by URI: ``https://geoui.org/ext/chart/v1.0.0``
Namespace prefix: ``chart:``

Required fields when used:
  - ``chart:layer`` — id of the layer to chart.

Optional fields:
  - ``chart:area`` — [x1, y1, x2, y2] AOI in the viewport's CRS.
  - ``chart:time`` — TimeWindow (range) for the chart axis.
  - ``chart:autoload`` — render immediately on open (default false).
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from geoui.core import GeoIntent, TimeWindow
from geoui.extensions.spec import ExtensionSpec

URI = "https://geoui.org/ext/chart/v1.0.0"
PREFIX = "chart"


class ChartFields(BaseModel):
    """Typed view of the ``chart:*`` fields on a GeoIntent."""

    layer: str = Field(description="Id of the layer to chart.")
    area: list[float] | None = Field(
        default=None, min_length=4, max_length=4, description="Area of interest [x1, y1, x2, y2] in the viewport CRS."
    )
    time: TimeWindow | None = Field(
        default=None, description="Chart time axis as a range {start, end}; never an instant."
    )
    autoload: bool = Field(default=False, description="Render the chart immediately on open.")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _time_must_be_range(self) -> Self:
        if self.time is not None and self.time.instant is not None:
            raise ValueError("chart:time must be a range (start/end); a single instant is not meaningful for a chart")
        return self


def extract(intent: GeoIntent) -> ChartFields | None:
    """Pull ``chart:*`` fields off an intent; None when none are present (declared or not)."""
    declared = URI in intent.geoui_extensions
    raw = intent.extension_fields(PREFIX)

    if not raw:
        return None
    if not declared:
        raise ValueError(f"GeoIntent has `{PREFIX}:*` fields but does not declare {URI} in geoui_extensions")

    stripped = {k.removeprefix(f"{PREFIX}:"): v for k, v in raw.items()}
    return ChartFields(**stripped)


def inject(intent: GeoIntent, fields: ChartFields) -> GeoIntent:
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
    extract(intent)


SPEC = ExtensionSpec(
    uri=URI,
    prefix=PREFIX,
    scope="intent",
    fields=ChartFields,
    summary="Open a time-series chart of one layer over an area of interest and a date range.",
)
