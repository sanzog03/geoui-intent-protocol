"""The one seam between the harness and an application under test."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability

from geoui import GeoIntent

#: What the application shows at the end of a turn, in the GeoIntent vocabulary
#: (layers + opacity, time, projection, compare / chart / styling fields). The
#: agent under test never sees this type; the application's
#: :meth:`BenchmarkApp.observe` produces it from whatever the agent left on
#: screen, so a URL reached by clicking and one reached by rendering an
#: intent are judged identically.
UIState = GeoIntent


@runtime_checkable
class BenchmarkApp(Protocol):
    """What an application provides to be benchmarked.

    ``agent_kinds`` names the agent variants under comparison (for Worldview:
    ``("geoui", "vlm")``). Everything else describes the application, not the
    agents: which layers it injects by itself, which tool names mean the
    agent went off to discover data, how to read its state back.
    """

    name: str
    agent_kinds: tuple[str, ...]
    #: Layers the application adds on its own (base imagery, reference
    #: overlays). Ignored by the state judge unless the expected state names them.
    auto_layers: frozenset[str]
    #: Tool names that mean "the agent did discovery"; on prompts marked
    #: fully specified these calls count as wasted work.
    discovery_tools: frozenset[str]

    def build_agent(
        self,
        kind: str,
        *,
        cdp_endpoint: str | None,
        extra_capabilities: Sequence[AbstractCapability],
    ) -> Agent[Any, Any]:
        """A fresh agent of ``kind``; ``extra_capabilities`` carries the harness's tracing."""
        ...

    def chatbot_role(self, kind: str) -> str:
        """One sentence describing the agent's role, for deepeval's conversational metrics."""
        ...

    def output_url(self, output: Any) -> str | None:
        """The application URL in a structured output, or ``None`` for a text-only turn."""
        ...

    def observe(self, url: str) -> UIState:
        """What the application shows at ``url`` (hidden layers dropped). Raises ``ValueError`` if unparseable."""
        ...


__all__ = ["BenchmarkApp", "UIState"]
