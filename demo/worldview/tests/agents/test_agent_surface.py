"""Golden test: what the model sees from each IESO agent must not drift.

``fixtures/agent_surface.json`` captures system prompts, bound config
descriptions, tool and capability lists, Playwright allow-lists and the
output-schema names/docstrings/field descriptions for both agents. Refactors
of the agent plumbing must leave it byte-identical. Regenerate deliberately
with ``uv run python scripts/capture_agent_surface.py``.

Requires the ``agents`` extra; skipped otherwise.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("akd")

from worldview.agents import geoui_agent, vlm_agent
from worldview.tests.agents._surface import surface

pytestmark = pytest.mark.agents

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "agent_surface.json").read_text())

VARIANTS = {
    "geoui": (geoui_agent.IESOWorldviewGeoUIAgent, geoui_agent),
    "vlm": (vlm_agent.IESOWorldviewVLMAgent, vlm_agent),
}


def _current(variant: str) -> dict:
    agent_cls, module = VARIANTS[variant]
    return surface(
        agent_cls,
        make_playwright_mcp=module.make_playwright_mcp,
        playwright_capability=module.playwright_capability,
    )


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_surface_matches_golden(variant):
    current = _current(variant)
    golden = GOLDEN[variant]
    # Compare key by key so a failure names the drifted surface.
    assert set(current) == set(golden)
    for key in golden:
        assert current[key] == golden[key], f"{variant}: {key} drifted from the golden"


def test_variants_share_discovery_plumbing():
    geoui, vlm = _current("geoui"), _current("vlm")
    assert geoui["capabilities"] == vlm["capabilities"]
    assert geoui["tools"][-3:] == vlm["tools"]
    assert geoui["model_name"] == vlm["model_name"]
    assert geoui["reasoning_effort"] == vlm["reasoning_effort"]


def test_variants_differ_only_where_intended():
    geoui, vlm = _current("geoui"), _current("vlm")
    assert geoui["tools"][:2] == ["geo_ui_render_intent_tool", "geo_ui_get_state_tool"]
    assert geoui["playwright_capability"]["allowed_tools"] == ["browser_navigate", "browser_evaluate"]
    assert len(vlm["playwright_capability"]["allowed_tools"]) == 11
    assert geoui["agent_name"] == "ieso_worldview_geo_ui_agent"
    assert vlm["agent_name"] == "ieso_worldview_vlm_agent"
