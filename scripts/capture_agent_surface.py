"""Regenerate ``demo/worldview/tests/agents/fixtures/agent_surface.json``.

Run only when a change to what the model sees is intentional::

    uv run python scripts/capture_agent_surface.py

Review the diff of the fixture before committing it.
"""

from __future__ import annotations

import json
from pathlib import Path

from worldview.tests.agents._surface import surface

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    from worldview.agents import geoui_agent, vlm_agent

    data = {
        "geoui": surface(
            geoui_agent.IESOWorldviewGeoUIAgent,
            make_playwright_mcp=geoui_agent.make_playwright_mcp,
            playwright_capability=geoui_agent.playwright_capability,
        ),
        "vlm": surface(
            vlm_agent.IESOWorldviewVLMAgent,
            make_playwright_mcp=vlm_agent.make_playwright_mcp,
            playwright_capability=vlm_agent.playwright_capability,
        ),
    }
    out = ROOT / "demo" / "worldview" / "tests" / "agents" / "fixtures" / "agent_surface.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
