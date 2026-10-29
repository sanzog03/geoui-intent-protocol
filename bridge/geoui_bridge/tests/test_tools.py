"""The three operations against a fake page: catalogue check, pre-declaration, payload shape, results."""

import pytest

from geoui import GeoIntent
from geoui.extensions import compare, raster_styling
from geoui_bridge import BridgeError
from geoui_bridge.tools import get_state, intent_payload, list_intent_extensions, render_intent

from ._fake_session import FakeSession


def _intent(**extra) -> GeoIntent:
    return GeoIntent.model_validate(
        {"time": {"instant": "2025-09-15"}, "layers": [{"id": "A", "opacity": 0.5}], **extra}
    )


async def test_render_declares_uris_sends_json_without_nulls_and_returns_the_settled_state():
    page = FakeSession()
    out = await render_intent(page, _intent(**{"compare:layers": [{"id": "B"}], "compare:mode": "spy"}))
    sent = page.calls[-1][1]
    assert sent["geoui_extensions"] == [compare.URI, raster_styling.URI]
    assert sent["time"] == {"instant": "2025-09-15"}  # start/end nulls dropped
    assert sent["layers"] == [{"id": "A", "visible": True, "opacity": 0.5}]
    assert sent["compare:layers"] == [{"id": "B"}] and sent["compare:mode"] == "spy"  # extras pass through as given
    assert out.settled is True
    assert [layer.id for layer in out.intent.layers] == ["A"]
    assert compare.extract(out.intent).mode == "spy"


async def test_render_refuses_what_the_page_did_not_attach_before_touching_it():
    page = FakeSession(extensions=("compare",))
    with pytest.raises(ValueError, match=r"\['raster-styling'\].*supported: compare"):
        await render_intent(page, _intent(layers=[{"id": "A", "raster-styling:min": 0}]))
    with pytest.raises(ValueError, match=r"unknown layer id\(s\) \['Z'\]"):
        await render_intent(page, _intent(layers=[{"id": "Z"}]))
    assert [name for name, _ in page.calls] == ["describe", "describe"]  # no render reached the page


async def test_render_passes_the_pages_refusal_on_as_a_value_error():
    page = FakeSession(refuse={"ok": False, "code": "unsupported_value", "error": "only one layer at a time"})
    with pytest.raises(ValueError, match="only one layer at a time"):
        await render_intent(page, _intent())


async def test_drifted_catalogue_is_a_bridge_error():
    page = FakeSession()
    page.catalogue["extensions"][0]["required"] = []
    with pytest.raises(BridgeError, match="differs from the library"):
        await list_intent_extensions(page)


async def test_list_and_get_state():
    page = FakeSession()
    listed = await list_intent_extensions(page)
    assert [e.name for e in listed.extensions] == ["compare", "raster-styling"]
    assert [layer.id for layer in listed.layers] == ["A", "B"] and listed.layers[0].time.period == "P1D"
    state = await get_state(page)
    assert state.intent.geoui_extensions == [compare.URI, raster_styling.URI] and state.intent.layers == []


def test_intent_payload_drops_none_but_keeps_false_and_zero():
    payload = intent_payload(_intent(layers=[{"id": "A", "visible": False, "opacity": 0.0}]))
    assert payload["layers"] == [{"id": "A", "visible": False, "opacity": 0.0}]
    assert "bbox" not in payload["viewport"] and payload["viewport"]["crs"] == "EPSG:4326"
