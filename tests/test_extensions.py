"""Extension specs, the declare-means-allowed rule, and the helpers consumers advertise with."""

import pytest

from geoui import GeoIntent, LayerRef, TimeWindow
from geoui.extensions import ALL, ExtensionSpec, chart, compare, declare, raster_styling, used_prefixes

ALL_URIS = [s.uri for s in ALL]


def _intent(**extra):
    return GeoIntent.model_validate(
        {"time": {"instant": "2025-09-15"}, "layers": [{"id": "A"}], **extra},
    )


class TestDeclareMeansAllowed:
    def test_declared_but_unused_extensions_extract_to_none(self):
        intent = _intent(geoui_extensions=ALL_URIS)
        assert compare.extract(intent) is None
        assert chart.extract(intent) is None
        compare.validate(intent)
        chart.validate(intent)
        raster_styling.validate(intent)

    def test_fields_without_declaration_still_raise(self):
        with pytest.raises(ValueError, match="does not declare"):
            compare.extract(_intent(**{"compare:layers": [{"id": "B"}]}))
        with pytest.raises(ValueError, match="does not declare"):
            chart.extract(_intent(**{"chart:layer": "A"}))
        with pytest.raises(ValueError, match="does not declare"):
            raster_styling.validate(_intent(layers=[{"id": "A", "raster-styling:min": 0.1}]))

    def test_declared_and_incomplete_raises_on_the_missing_field(self):
        with pytest.raises(ValueError, match="layers"):
            compare.extract(_intent(geoui_extensions=[compare.URI], **{"compare:mode": "spy"}))
        with pytest.raises(ValueError, match="layer"):
            chart.extract(_intent(geoui_extensions=[chart.URI], **{"chart:autoload": True}))

    def test_declared_and_complete_extracts(self):
        intent = _intent(
            geoui_extensions=ALL_URIS, **{"compare:layers": [{"id": "B"}], "compare:time": {"instant": "2025-09-14"}}
        )
        fields = compare.extract(intent)
        assert [layer.id for layer in fields.layers] == ["B"] and fields.time == TimeWindow(instant="2025-09-14")
        assert fields.mode == "swipe" and fields.value == 50 and fields.active_side == "A"


class TestSpecs:
    def test_all_lists_the_three_shipped_extensions_in_order(self):
        assert [s.prefix for s in ALL] == ["compare", "chart", "raster-styling"]
        assert [s.scope for s in ALL] == ["intent", "intent", "layer"]
        assert all(isinstance(s, ExtensionSpec) and s.uri.startswith("https://geoui.org/ext/") for s in ALL)

    def test_describe_is_self_contained(self):
        d = compare.SPEC.describe()
        assert d["name"] == "compare" and d["uri"] == compare.URI and d["scope"] == "intent"
        assert d["keys"] == ["compare:layers", "compare:active_side", "compare:time", "compare:mode", "compare:value"]
        assert d["required"] == ["compare:layers"]
        assert d["fields_schema"]["properties"]["mode"]["enum"] == ["swipe", "spy", "opacity"]
        assert "LayerRef" in d["fields_schema"]["$defs"]  # nested types travel with the schema
        assert d["summary"]
        for spec in ALL:
            assert all(spec.fields.model_fields[f].description for f in spec.fields.model_fields), spec.prefix


class TestHelpers:
    def test_used_prefixes_sees_intent_and_layer_keys_including_unknown_ones(self):
        intent = _intent(
            layers=[{"id": "A", "raster-styling:min": 1}], **{"compare:layers": [{"id": "B"}], "foo:bar": 1}
        )
        assert used_prefixes(intent) == {"compare", "raster-styling", "foo"}
        assert used_prefixes(_intent()) == set()

    def test_declare_merges_without_duplicates_and_does_not_mutate(self):
        intent = _intent(geoui_extensions=[chart.URI])
        out = declare(intent, [compare.URI, chart.URI, compare.URI])
        assert out.geoui_extensions == [chart.URI, compare.URI]
        assert intent.geoui_extensions == [chart.URI]
        assert declare(out, [compare.URI]) is out  # nothing to add → same object

    def test_declare_keeps_namespaced_fields(self):
        intent = _intent(**{"compare:layers": [{"id": "B"}]})
        out = declare(intent, [compare.URI])
        assert compare.extract(out).layers == [LayerRef(id="B")]
