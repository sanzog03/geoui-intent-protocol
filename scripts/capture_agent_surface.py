"""Regenerate ``demo/worldview/tests/agents/fixtures/agent_surface.json``.

Run only when a change to what the model sees is intentional (a plugin
submodule bump, a re-exported skill, a prompt or tool change)::

    uv run python scripts/capture_agent_surface.py

Review the diff of the fixture before committing it.
"""

from __future__ import annotations

import json
from pathlib import Path

from worldview.agents import geoui_spec, vlm_spec
from worldview.tests.agents._surface import CDP_ENDPOINT, DUMMY_ENV, surface

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    data = {
        "geoui": surface(geoui_spec(cdp_endpoint=CDP_ENDPOINT, environ=DUMMY_ENV)),
        "vlm": surface(vlm_spec(cdp_endpoint=CDP_ENDPOINT, environ=DUMMY_ENV)),
    }
    out = ROOT / "demo" / "worldview" / "tests" / "agents" / "fixtures" / "agent_surface.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
