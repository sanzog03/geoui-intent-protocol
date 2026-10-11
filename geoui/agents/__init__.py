"""IESO Worldview reference agents and benchmark harness (optional extra ``agents``).

Two pydantic-ai agents that share the same discovery tools and differ only
in the interaction mechanism:

- :class:`IESOWorldviewGeoUIAgent` — drives Worldview through the GeoUI
  protocol tools (treatment).
- :class:`IESOWorldviewVLMAgent` — drives Worldview through Playwright
  screenshots / snapshots / clicks (baseline).

Importing this package requires ``akd-ext`` (``uv sync --extra agents``).
"""

from geoui.agents._akd_tools import GeoUIGetStateTool, GeoUIRenderIntentTool
from geoui.agents.geoui_agent import (
    IESOWorldviewGeoUIAgent,
    IESOWorldviewGeoUIAgentConfig,
    IESOWorldviewGeoUIAgentInputSchema,
    IESOWorldviewGeoUIAgentOutputSchema,
)
from geoui.agents.vlm_agent import (
    IESOWorldviewVLMAgent,
    IESOWorldviewVLMAgentConfig,
    IESOWorldviewVLMAgentInputSchema,
    IESOWorldviewVLMAgentOutputSchema,
)

__all__ = [
    "GeoUIGetStateTool",
    "GeoUIRenderIntentTool",
    "IESOWorldviewGeoUIAgent",
    "IESOWorldviewGeoUIAgentConfig",
    "IESOWorldviewGeoUIAgentInputSchema",
    "IESOWorldviewGeoUIAgentOutputSchema",
    "IESOWorldviewVLMAgent",
    "IESOWorldviewVLMAgentConfig",
    "IESOWorldviewVLMAgentInputSchema",
    "IESOWorldviewVLMAgentOutputSchema",
]
