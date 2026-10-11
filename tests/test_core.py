"""Unit tests for the GeoUI protocol core models."""

import pytest
from pydantic import ValidationError

from geoui import GEOUI_PROTOCOL_VERSION, GeoIntent, LayerRef, TimeWindow, Viewport, __version__


class TestTimeWindow:
    def test_instant_only(self):
        tw = TimeWindow(instant="2025-09-15")
        assert tw.instant == "2025-09-15" and tw.start is None and tw.end is None

    def test_range_only(self):
        tw = TimeWindow(start="2025-09-01", end="2025-09-30")
        assert tw.instant is None

    def test_all_none_means_app_default(self):
        assert TimeWindow().instant is None

    def test_instant_and_range_are_exclusive(self):
        with pytest.raises(ValidationError, match="mutually exclusive"):
            TimeWindow(instant="2025-09-15", start="2025-09-01", end="2025-09-30")

    @pytest.mark.parametrize("kwargs", [{"start": "2025-09-01"}, {"end": "2025-09-30"}])
    def test_half_range_rejected(self, kwargs):
        with pytest.raises(ValidationError, match="both be set"):
            TimeWindow(**kwargs)


class TestLayerRef:
    def test_defaults(self):
        layer = LayerRef(id="MODIS_Aqua_Aerosol")
        assert layer.visible is True and layer.opacity is None

    @pytest.mark.parametrize("opacity", [-0.1, 1.1])
    def test_opacity_bounds(self, opacity):
        with pytest.raises(ValidationError):
            LayerRef(id="L", opacity=opacity)

    def test_extension_fields_filters_by_prefix(self):
        layer = LayerRef.model_validate(
            {"id": "L", "raster-styling:palettes": ["red"], "raster-styling:min": 0, "other:x": 1}
        )
        assert layer.extension_fields("raster-styling") == {"raster-styling:palettes": ["red"], "raster-styling:min": 0}
        assert layer.extension_fields("missing") == {}


class TestViewport:
    def test_defaults(self):
        vp = Viewport()
        assert vp.bbox is None and vp.crs == "EPSG:4326"

    @pytest.mark.parametrize("bbox", [[0, 0, 1], [0, 0, 1, 1, 1]])
    def test_bbox_must_have_four_values(self, bbox):
        with pytest.raises(ValidationError):
            Viewport(bbox=bbox)


class TestGeoIntent:
    def test_defaults_carry_protocol_version(self):
        intent = GeoIntent()
        assert intent.geoui_version == GEOUI_PROTOCOL_VERSION == "1.0.0"
        assert intent.geoui_extensions == [] and intent.layers == [] and intent.time is None

    def test_namespaced_extras_round_trip_through_model_dump(self):
        doc = {
            "geoui_extensions": ["https://geoui.org/ext/compare/v1.0.0"],
            "viewport": {"bbox": [-125, 32, -114, 42], "crs": "EPSG:4326"},
            "time": {"instant": "2025-09-15"},
            "layers": [{"id": "MODIS_Aqua_Aerosol", "opacity": 0.8}],
            "compare:mode": "swipe",
            "compare:value": 60,
        }
        intent = GeoIntent.model_validate(doc)
        assert intent.extension_fields("compare") == {"compare:mode": "swipe", "compare:value": 60}
        again = GeoIntent.model_validate(intent.model_dump(by_alias=True))
        assert again == intent

    def test_package_version_is_exported(self):
        assert __version__
