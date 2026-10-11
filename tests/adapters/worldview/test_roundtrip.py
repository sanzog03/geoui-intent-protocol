"""Round-trip tests for the Worldview adapter: GeoIntent → URL → GeoIntent."""

import pytest

from geoui.adapters.worldview import intent_to_url, url_to_intent
from geoui.core import GeoIntent, LayerRef, TimeWindow, Viewport
from geoui.extensions import chart, compare, raster_styling


@pytest.fixture
def simple_intent() -> GeoIntent:
    return GeoIntent(
        viewport=Viewport(bbox=[-125, 32, -114, 42], crs="EPSG:4326"),
        time=TimeWindow(instant="2025-09-15"),
        layers=[LayerRef(id="MODIS_Aqua_Aerosol", opacity=0.8)],
    )


@pytest.fixture
def rich_intent() -> GeoIntent:
    intent = GeoIntent(
        geoui_extensions=[raster_styling.URI],
        viewport=Viewport(bbox=[-125, 32, -114, 42], crs="EPSG:4326"),
        time=TimeWindow(instant="2025-09-15"),
        layers=[
            LayerRef.model_validate(
                {
                    "id": "MODIS_Aqua_Aerosol",
                    "opacity": 0.8,
                    "raster-styling:palettes": ["red_1"],
                    "raster-styling:min": 0,
                    "raster-styling:max": 2,
                    "raster-styling:squash": True,
                }
            )
        ],
    )
    intent = compare.inject(
        intent,
        compare.CompareFields(
            layers=[LayerRef(id="MODIS_Aqua_Aerosol")],
            time=TimeWindow(instant="2025-09-14"),
            mode="swipe",
            value=60,
        ),
    )
    return chart.inject(
        intent,
        chart.ChartFields(
            layer="MODIS_Aqua_Aerosol",
            area=[-125, 32, -114, 42],
            time=TimeWindow(start="2025-09-01", end="2025-09-30"),
            autoload=True,
        ),
    )


class TestIntentToUrl:
    def test_simple_intent_renders_url(self, simple_intent):
        url = intent_to_url(simple_intent)
        assert url.startswith("https://")
        assert "MODIS_Aqua_Aerosol" in url
        assert "t=2025-09-15" in url

    def test_rich_intent_renders_extension_params(self, rich_intent):
        url = intent_to_url(rich_intent)
        # compare → ca/l1/t1/cm/cv, chart → cha/chl, raster-styling → palettes
        for fragment in ("ca=", "l1=", "cm=swipe", "cv=60", "cha=true", "palettes"):
            assert fragment in url

    def test_embed_mode_off_by_default(self, simple_intent):
        url = intent_to_url(simple_intent)
        assert "em=" not in url

    def test_embed_mode_opt_in(self, simple_intent):
        url = intent_to_url(simple_intent, embed_mode=True)
        assert "em=true" in url

    def test_antimeridian_chart_area_renders_unwrapped(self, simple_intent):
        intent = chart.inject(
            simple_intent,
            chart.ChartFields(layer="MODIS_Aqua_Aerosol", area=[120, -60, -70, 65]),
        )
        url = intent_to_url(intent)
        assert "chc=120,-60,290,65" in url


class TestUrlToIntent:
    def test_round_trip_simple(self, simple_intent):
        rendered = intent_to_url(simple_intent)
        parsed = url_to_intent(rendered)

        assert parsed.viewport.bbox == simple_intent.viewport.bbox
        assert str(parsed.time.instant) == "2025-09-15"
        # build_url auto-injects base reflectance / reference overlay layers,
        # so assert on membership rather than the exact layer list.
        layers_by_id = {layer.id: layer for layer in parsed.layers}
        assert "MODIS_Aqua_Aerosol" in layers_by_id
        assert layers_by_id["MODIS_Aqua_Aerosol"].opacity == 0.8

    def test_round_trip_declares_extensions(self, rich_intent):
        rendered = intent_to_url(rich_intent)
        parsed = url_to_intent(rendered)

        declared = set(parsed.geoui_extensions)
        assert {compare.URI, chart.URI, raster_styling.URI} <= declared

        cmp = compare.extract(parsed)
        assert cmp is not None
        assert cmp.mode == "swipe"
        assert cmp.value == 60

        ch = chart.extract(parsed)
        assert ch is not None
        assert ch.layer == "MODIS_Aqua_Aerosol"
        assert ch.autoload is True

    def test_round_trip_antimeridian_chart_area(self, simple_intent):
        intent = chart.inject(
            simple_intent,
            chart.ChartFields(layer="MODIS_Aqua_Aerosol", area=[120, -60, -70, 65]),
        )
        rendered = intent_to_url(intent)
        parsed = url_to_intent(rendered)

        ch = chart.extract(parsed)
        assert ch is not None
        assert ch.area == [120, -60, 290, 65]

    def test_round_trip_compare_time_defaults_to_side_a(self, simple_intent):
        intent = compare.inject(
            simple_intent,
            compare.CompareFields(layers=[LayerRef(id="MODIS_Aqua_Aerosol")], mode="swipe"),
        )
        rendered = intent_to_url(intent)
        assert "t1=2025-09-15" in rendered

        parsed = url_to_intent(rendered)
        cmp = compare.extract(parsed)
        assert cmp is not None
        assert str(cmp.time.instant) == "2025-09-15"
