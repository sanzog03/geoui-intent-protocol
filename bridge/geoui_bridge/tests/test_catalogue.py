"""The page's catalogue is checked against the library, and intents are prepared the consumer-side way."""

import json
from pathlib import Path

import pytest

from geoui import GeoIntent
from geoui.extensions import chart, compare, raster_styling
from geoui_bridge import BridgeError, Catalogue, check_catalogue, prepare_intent
from geoui_bridge.cdp import BridgeConfig, config_from_env

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "schemas" / "extensions"


def _catalogue(*names: str, layers=()) -> Catalogue:
    """A catalogue built from the committed schema JSON, the way the SDK embeds it."""
    exts = [json.loads((SCHEMAS / f"{n}.json").read_text()) for n in names]
    return Catalogue.model_validate(
        {"version": "0.1.0", "protocol": "1.0.0", "extensions": exts, "layers": list(layers)}
    )


def _intent(**extra) -> GeoIntent:
    return GeoIntent.model_validate({"time": {"instant": "2025-09-15"}, "layers": [{"id": "A"}], **extra})


class TestCheckCatalogue:
    def test_committed_documents_pass(self):
        check_catalogue(_catalogue("compare", "chart", "raster_styling"))

    def test_an_empty_catalogue_passes(self):
        check_catalogue(Catalogue(version="0.1.0", protocol="1.0.0"))

    def test_unknown_extension_is_refused(self):
        cat = _catalogue("compare")
        cat.extensions[0].uri = "https://example.org/ext/elevation/v1"
        with pytest.raises(BridgeError, match="does not know"):
            check_catalogue(cat)

    def test_drifted_document_is_refused_naming_the_keys(self):
        cat = _catalogue("compare")
        cat.extensions[0].summary = "something else"
        cat.extensions[0].required = []
        with pytest.raises(BridgeError, match=r"\['required', 'summary'\]"):
            check_catalogue(cat)


class TestPrepareIntent:
    def test_declares_the_page_extensions_and_keeps_fields(self):
        cat = _catalogue("compare", "raster_styling")
        out = prepare_intent(_intent(**{"compare:layers": [{"id": "B"}]}), cat)
        assert out.geoui_extensions == [compare.URI, raster_styling.URI]
        assert compare.extract(out).layers[0].id == "B"

    def test_unsupported_prefix_names_the_supported_ones(self):
        cat = _catalogue("compare", "raster_styling")
        with pytest.raises(ValueError) as exc:
            prepare_intent(_intent(**{"chart:layer": "A"}), cat)
        assert str(exc.value) == (
            "extension(s) ['chart'] are not available in this app; supported: compare, raster-styling "
            "(see geo_ui_list_intent_extensions_tool)"
        )

    def test_layer_scoped_unsupported_prefix_is_seen(self):
        with pytest.raises(ValueError, match=r"\['elevation'\]"):
            prepare_intent(_intent(layers=[{"id": "A", "elevation:exaggeration": 2}]), _catalogue("compare"))

    def test_crs_must_be_geographic(self):
        with pytest.raises(ValueError, match="EPSG:3857.*use EPSG:4326"):
            prepare_intent(_intent(viewport={"bbox": None, "crs": "EPSG:3857"}), _catalogue())

    def test_unknown_layer_ids_on_root_and_in_compare_layers(self):
        cat = _catalogue("compare", layers=[{"id": "A", "title": "A"}, {"id": "B", "title": "B"}])
        with pytest.raises(ValueError) as exc:
            prepare_intent(_intent(layers=[{"id": "A"}, {"id": "Z"}], **{"compare:layers": [{"id": "Q"}]}), cat)
        assert (
            str(exc.value) == "unknown layer id(s) ['Z', 'Q']; known ids: A, B (see geo_ui_list_intent_extensions_tool)"
        )

    def test_without_a_layer_catalogue_any_id_passes(self):
        assert prepare_intent(_intent(layers=[{"id": "anything"}]), _catalogue()).layers[0].id == "anything"

    def test_typed_validation_runs_for_declared_extensions(self):
        with pytest.raises(ValueError, match="layers"):
            prepare_intent(_intent(**{"compare:mode": "spy"}), _catalogue("compare"))
        with pytest.raises(ValueError, match="range"):
            prepare_intent(
                _intent(**{"chart:layer": "A", "chart:time": {"instant": "2025-01-01"}}), _catalogue("chart")
            )
        assert chart.extract(prepare_intent(_intent(**{"chart:layer": "A"}), _catalogue("chart"))).layer == "A"

    def test_incoming_declarations_are_merged_not_trusted(self):
        out = prepare_intent(_intent(geoui_extensions=["https://example.org/ext/foo/v1"]), _catalogue("compare"))
        assert out.geoui_extensions == ["https://example.org/ext/foo/v1", compare.URI]


class TestConfig:
    def test_defaults_and_env(self):
        assert config_from_env({}) == BridgeConfig(cdp_endpoint="http://localhost:9222", app_url=None)
        cfg = config_from_env(
            {"PLAYWRIGHT_CDP_ENDPOINT": "http://127.0.0.1:9333", "GEOUI_APP_URL": "http://localhost:5173/"}
        )
        assert cfg == BridgeConfig(cdp_endpoint="http://127.0.0.1:9333", app_url="http://localhost:5173/")
