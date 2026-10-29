"""Live round trip through a real Chromium and a real window.geoui page.

Skipped unless ``PLAYWRIGHT_CDP_ENDPOINT`` answers and ``GEOUI_APP_URL`` is set
(start the MapLibre demo with ``npm run dev`` and Chromium with
``source demo/chromium.sh && ensure_chromium``).
"""

import os

import httpx
import pytest

from maplibre import BridgeError, bridge, config_from_env

pytestmark = pytest.mark.integration

CONFIG = config_from_env()


def _cdp_up() -> bool:
    try:
        return httpx.get(f"{CONFIG.cdp_endpoint}/json/version", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


needs_browser = pytest.mark.skipif(
    not (os.getenv("GEOUI_APP_URL") and _cdp_up()),
    reason="needs GEOUI_APP_URL and a Chromium on PLAYWRIGHT_CDP_ENDPOINT",
)


@needs_browser
async def test_describe_get_state_render_round_trip():
    async with bridge(CONFIG) as session:
        catalogue = await session.describe()
        assert catalogue["protocol"] == "1.0.0" and isinstance(catalogue["extensions"], list)
        before = await session.get_state()
        assert before["geoui_version"] == "1.0.0"
        result = await session.render({**before, "time": {"instant": "2025-09-15"}})
        assert result["ok"] is True
        assert (await session.get_state())["time"]["instant"] == "2025-09-15"
        with pytest.raises(ValueError):
            await session.render({"layers": [{"id": "definitely-not-a-layer"}], "chart:layer": "x"})


@needs_browser
async def test_state_persists_across_sessions_and_the_tab_survives_disconnect():
    async with bridge(CONFIG) as session:
        before = await session.get_state()
        await session.render({**before, "time": {"instant": "2024-07-04"}})
    async with bridge(CONFIG) as session:  # a new connection finds the same tab with the same state
        assert (await session.get_state())["time"]["instant"] == "2024-07-04"


async def test_unreachable_endpoint_is_a_bridge_error():
    from maplibre.cdp import BridgeConfig

    with pytest.raises(BridgeError, match="cannot attach"):
        async with bridge(BridgeConfig(cdp_endpoint="http://127.0.0.1:1")):
            pass
