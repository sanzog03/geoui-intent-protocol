"""Golden test: what the model sees from each Worldview agent must not drift.

``fixtures/agent_surface.json`` captures, per variant, the system prompts
(the vendored skills and the VLM browser addendum), the in-process tool
names / descriptions / parameter schemas, the capability list (remote MCP
ids and URLs, the Playwright allow-list, reasoning effort) and the output
tool names and schemas. A refactor of the agent plumbing, a bump of the
plugin submodule or a re-export of the mio skill must be a deliberate
change: regenerate with ``uv run python scripts/capture_agent_surface.py``
and review the fixture diff.
"""

import json
from pathlib import Path

import pytest

from worldview.agents import geoui_spec, vlm_spec
from worldview.tests.agents._surface import CDP_ENDPOINT, DUMMY_ENV, surface

pytestmark = pytest.mark.agents

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "agent_surface.json").read_text())

VARIANTS = {"geoui": geoui_spec, "vlm": vlm_spec}


def _current(variant: str) -> dict:
    return surface(VARIANTS[variant](cdp_endpoint=CDP_ENDPOINT, environ=DUMMY_ENV))


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_surface_matches_golden(variant):
    current = _current(variant)
    golden = GOLDEN[variant]
    assert set(current) == set(golden)
    for key in golden:  # key by key so a failure names the drifted surface
        assert current[key] == golden[key], f"{variant}: {key} drifted from the golden"


def test_variants_share_discovery_plumbing():
    geoui, vlm = _current("geoui"), _current("vlm")
    remote = lambda s: [c for c in s["capabilities"] if c["type"] == "MCP" and c["id"] != "playwright_mcp"]
    assert remote(geoui) == remote(vlm)
    assert {c["id"] for c in remote(geoui)} >= {
        "cmr",
        "ieso-validation",
        "umm-vis-lookup",
        "earthdata-search",
        "sde-search",
    }
    assert all(c["id"] not in ("geoui", "worldview-permalink") for c in remote(geoui))
    assert geoui["model_name"] == vlm["model_name"] == "gpt-5.2"
    thinking = lambda s: [c for c in s["capabilities"] if c["type"] == "Thinking"]
    assert thinking(geoui) == thinking(vlm) and thinking(geoui)[0]["effort"] == "medium"


def test_variants_differ_only_where_intended():
    geoui, vlm = _current("geoui"), _current("vlm")
    assert geoui["agent_name"] == "worldview_geoui_agent"
    assert vlm["agent_name"] == "worldview_vlm_agent"

    assert set(geoui["local_tools"]) == {
        "geo_ui_render_intent_tool",
        "geo_ui_get_state_tool",
        "worldview_permalink_tool",
        "list_references",
        "read_reference",
    }
    assert set(vlm["local_tools"]) == {"list_references", "read_reference"}  # no URL builder: UI only

    pw = lambda s: next(c for c in s["capabilities"] if c["id"] == "playwright_mcp")
    assert pw(geoui)["allowed_tools"] == ["browser_navigate", "browser_evaluate"]
    assert len(pw(vlm)["allowed_tools"]) == 11
    assert pw(geoui)["local"]["args"][-2:] == ["--cdp-endpoint", CDP_ENDPOINT]
    assert pw(vlm)["local"]["args"][-4:] == ["--cdp-endpoint", CDP_ENDPOINT, "--timeout-action", "15000"]
    assert geoui["retries"] == 1 and vlm["retries"] == 3  # the UI-driving baseline needs slack for click timeouts
    assert pw(geoui)["local"]["max_retries"] == 1 and pw(vlm)["local"]["max_retries"] == 3

    assert len(geoui["system_prompts"]) == 1 and geoui["system_prompts"][0].startswith("# ROLE")
    assert len(vlm["system_prompts"]) == 2 and vlm["system_prompts"][1].startswith("# BROWSER INTERACTION")
    assert "geo_ui_render_intent_tool" in geoui["system_prompts"][0]
    assert "geo_ui" not in vlm["system_prompts"][0]

    assert [t["name"] for t in geoui["output_tools"]] == ["final_result_GeoUIAgentOutput", "final_result_TextOutput"]
    assert [t["name"] for t in vlm["output_tools"]] == ["final_result_VLMAgentOutput", "final_result_TextOutput"]


def test_no_akd_anywhere():
    import sys

    _current("geoui")
    _current("vlm")
    assert not [m for m in sys.modules if m.split(".")[0] in ("akd", "akd_ext")]
