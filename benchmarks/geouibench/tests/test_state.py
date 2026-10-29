"""The state judge compares what the UI shows with what a scenario expects.

Everything here is built from GeoIntent directly: the judge must not know any
application, and it must not care how an agent reached the state.
"""

from datetime import date

import pytest

from geoui import GeoIntent, LayerRef, TimeWindow, Viewport
from geoui.extensions import chart, compare, raster_styling
from geouibench.state import (
    ChartExpectation,
    CompareExpectation,
    ExpectedState,
    StateMatch,
    StylingExpectation,
    checkpoint_reached,
    compare_state,
    judge_url,
)

AOD = "MODIS_Aqua_Aerosol_Optical_Depth_3km"
TRUE_COLOR = "MODIS_Terra_CorrectedReflectance_TrueColor"
COAST = "Coastlines_15m"
AUTO = frozenset({TRUE_COLOR, COAST})


def intent(*layers: LayerRef, time: str | None = "2025-09-15", crs: str = "EPSG:4326") -> GeoIntent:
    return GeoIntent(
        viewport=Viewport(bbox=[-125, 24, -66, 50], crs=crs),
        time=TimeWindow(instant=time) if time else None,
        layers=list(layers),
    )


def test_layer_and_date_match_is_a_full_score():
    observed = intent(LayerRef(id=TRUE_COLOR), LayerRef(id=AOD, opacity=1.0), LayerRef(id=COAST))
    expected = ExpectedState(layers={AOD: None}, time=date(2025, 9, 15))
    match = compare_state(observed, expected, auto_layers=AUTO)
    assert match == StateMatch(matched=[f"layer:{AOD}", "time"], missed=[], score=1.0, error=None)


def test_missing_layer_and_wrong_date_are_listed():
    observed = intent(LayerRef(id=TRUE_COLOR), time="2025-09-14")
    expected = ExpectedState(layers={AOD: None}, time=date(2025, 9, 15))
    match = compare_state(observed, expected, auto_layers=AUTO)
    assert match.matched == []
    assert match.missed == [f"layer:{AOD}", "time"]
    assert match.score == 0.0


def test_opacity_none_equals_full_and_other_values_must_match():
    observed = intent(LayerRef(id=AOD), LayerRef(id="Reference_Labels_15m", opacity=0.6))
    expected = ExpectedState(layers={AOD: 1.0, "Reference_Labels_15m": 0.8}, time=None)
    match = compare_state(observed, expected, auto_layers=AUTO)
    assert match.matched == [f"layer:{AOD}"]
    assert match.missed == ["layer:Reference_Labels_15m"]


def test_hidden_layers_do_not_count_as_present():
    observed = intent(LayerRef(id=AOD, visible=False))
    expected = ExpectedState(layers={AOD: None})
    assert compare_state(observed, expected, auto_layers=AUTO).missed == [f"layer:{AOD}"]


def test_auto_layer_named_in_expected_is_judged_like_any_other():
    observed = intent(LayerRef(id=TRUE_COLOR, opacity=1.0))
    expected = ExpectedState(layers={TRUE_COLOR: 1.0, COAST: None})
    match = compare_state(observed, expected, auto_layers=AUTO)
    assert match.matched == [f"layer:{TRUE_COLOR}"]
    assert match.missed == [f"layer:{COAST}"]


@pytest.mark.parametrize(
    "raw",
    ["2025-09-15", "2025-09-15-T03:06:50Z", "2025-09-15T23:59:59+00:00", "2025-09-15T03:06:50"],
)
def test_time_is_compared_as_a_utc_date_from_any_spelling(raw):
    observed = intent(time=raw)
    assert compare_state(observed, ExpectedState(time=date(2025, 9, 15)), auto_layers=AUTO).score == 1.0


def test_crs_is_judged_when_expected():
    observed = intent(crs="EPSG:3413")
    assert compare_state(observed, ExpectedState(crs="EPSG:3413"), auto_layers=AUTO).matched == ["crs"]
    assert compare_state(observed, ExpectedState(crs="EPSG:4326"), auto_layers=AUTO).missed == ["crs"]


def test_bbox_is_never_judged():
    observed = intent()
    expected = ExpectedState()
    assert compare_state(observed, expected, auto_layers=AUTO) == StateMatch(matched=[], missed=[], score=1.0)


def test_compare_extension_fields():
    base = intent(LayerRef(id=AOD))
    observed = compare.inject(
        base,
        compare.CompareFields(layers=[LayerRef(id=AOD)], time=TimeWindow(instant="2025-09-14"), mode="swipe"),
    )
    expected = ExpectedState(compare=CompareExpectation(time=date(2025, 9, 14), mode="swipe", layers=[AOD]))
    match = compare_state(observed, expected, auto_layers=AUTO)
    assert match.matched == ["compare", "compare.time", "compare.mode", f"compare.layer:{AOD}"]
    assert match.score == 1.0

    off = compare_state(base, expected, auto_layers=AUTO)
    assert off.matched == []
    assert off.missed == ["compare", "compare.time", "compare.mode", f"compare.layer:{AOD}"]


def test_chart_extension_fields():
    base = intent(LayerRef(id="MOD13Q1_NDVI_16Day"))
    observed = chart.inject(
        base,
        chart.ChartFields(
            layer="MOD13Q1_NDVI_16Day",
            area=[-125, 30, -100, 49],
            time=TimeWindow(start="2024-04-01", end="2024-10-31"),
            autoload=True,
        ),
    )
    expected = ExpectedState(
        chart=ChartExpectation(
            layer="MOD13Q1_NDVI_16Day", start=date(2024, 4, 1), end=date(2024, 10, 31), autoload=True
        )
    )
    match = compare_state(observed, expected, auto_layers=AUTO)
    assert match.missed == []
    assert match.matched == ["chart", "chart.layer", "chart.start", "chart.end", "chart.autoload"]


def test_styling_on_a_layer():
    styled = raster_styling.inject(LayerRef(id=AOD), raster_styling.RasterStylingFields(min=0, max=2, squash=True))
    observed = raster_styling.declare(intent(styled))
    expected = ExpectedState(styling=StylingExpectation(layer=AOD, min=0, max=2, squash=True))
    match = compare_state(observed, expected, auto_layers=AUTO)
    assert match.missed == []
    assert match.matched == ["styling", "styling.min", "styling.max", "styling.squash"]

    plain = compare_state(intent(LayerRef(id=AOD)), expected, auto_layers=AUTO)
    assert plain.missed == ["styling", "styling.min", "styling.max", "styling.squash"]


def test_score_is_the_fraction_of_checks_matched():
    observed = intent(LayerRef(id=AOD), time="2025-09-15")
    expected = ExpectedState(layers={AOD: None, "Nope": None}, time=date(2025, 9, 15), crs="EPSG:3413")
    match = compare_state(observed, expected, auto_layers=AUTO)
    assert match.score == pytest.approx(2 / 4)


def test_checkpoint_reached_requires_a_full_match():
    observed = intent(LayerRef(id=AOD))
    assert checkpoint_reached(observed, ExpectedState(layers={AOD: None}), auto_layers=AUTO)
    assert not checkpoint_reached(observed, ExpectedState(layers={AOD: None}, crs="EPSG:3413"), auto_layers=AUTO)


class _App:
    auto_layers = AUTO

    def observe(self, url):
        if url == "good":
            return intent(LayerRef(id=AOD))
        raise ValueError(f"cannot parse {url}")


def test_judge_url_uses_the_app_and_reports_parse_failures():
    good = judge_url(_App(), "good", ExpectedState(layers={AOD: None}))
    assert good.score == 1.0
    bad = judge_url(_App(), "garbage", ExpectedState(layers={AOD: None}))
    assert bad.score == 0.0
    assert bad.matched == []
    assert bad.missed == [f"layer:{AOD}"]
    assert "cannot parse garbage" in (bad.error or "")
    none = judge_url(_App(), None, ExpectedState(layers={AOD: None}))
    assert none.score == 0.0 and none.error == "no URL"


def test_expected_state_rejects_unknown_fields():
    with pytest.raises(ValueError):
        ExpectedState(bbox=[0, 0, 1, 1])
