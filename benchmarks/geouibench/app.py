"""The one seam between the utility and an application under test.

An application is benchmarked from an *app directory* (see
:mod:`geouibench.appdir`) whose ``app.py`` exposes one object satisfying
:class:`BenchmarkApp`. Nothing else in the utility knows the application.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability

from geoui import GeoIntent

if TYPE_CHECKING:  # datasets imports state imports this module; the annotation is enough
    from geouibench.datasets import Budgets

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

    ``agent_kinds`` names the agent variants under comparison; the first one
    is the reference the summary's ratios are relative to. Everything else
    describes the application, not the agents: which layers it injects by
    itself, which tool names mean the agent went off to discover data, how to
    read its state back, and the per-turn budgets the efficiency metrics
    score every kind against.

    Optionally an app may also define ``prepare(self) -> Mapping[str, str]``:
    called once by ``geouibench run`` before the agents start (launch a
    browser, warm remote services, check prerequisites); the mapping it
    returns is added to the environment of the benchmark processes. Apps
    without setup simply omit it.

    Apps whose state does not live in a URL define
    ``async snapshot(self, cdp_endpoint: str | None) -> str | None`` instead of
    returning anything from ``output_url``: the runner calls it after every
    turn that ended without a handle, and whatever string it returns (for
    example the state itself, serialised) is stored as the turn's handle and
    later passed to ``observe``. Scoring runs offline from the stored handles,
    so a handle must carry everything ``observe`` needs.
    """

    name: str
    agent_kinds: tuple[str, ...]
    #: Layers the application adds on its own (base imagery, reference
    #: overlays). Ignored by the state judge unless the expected state names them.
    auto_layers: frozenset[str]
    #: Tool names that mean "the agent did discovery"; on prompts marked
    #: fully specified these calls count as wasted work.
    discovery_tools: frozenset[str]
    #: Per-turn budgets for every golden that does not override them; the same
    #: for every agent kind (a fixed yardstick, never derived from one agent's runs).
    budgets: Budgets

    def build_agent(
        self,
        kind: str,
        *,
        cdp_endpoint: str | None,
        extra_capabilities: Sequence[AbstractCapability],
    ) -> Agent[Any, Any]:
        """A fresh agent of ``kind``; ``extra_capabilities`` carries the utility's tracing."""
        ...

    def chatbot_role(self, kind: str) -> str:
        """One sentence describing the agent's role, for deepeval's conversational metrics."""
        ...

    def output_url(self, output: Any) -> str | None:
        """A handle for the state the turn ended in, or ``None``.

        For URL-state applications: the URL in a structured output (or found
        in the text). It is any string ``observe`` can read back; apps whose
        state is not in a URL return ``None`` here and define ``snapshot``.
        """
        ...

    def observe(self, url: str) -> UIState:
        """What the application shows at the handle ``url`` (hidden layers dropped). Raises ``ValueError`` if unreadable."""
        ...


def prepare_app(app: BenchmarkApp) -> dict[str, str]:
    """Run the app's optional ``prepare()`` hook and return the environment it asks for."""
    hook = getattr(app, "prepare", None)
    if hook is None:
        return {}
    env: Mapping[str, str] | None = hook()
    return dict(env or {})


async def snapshot_app(app: BenchmarkApp, cdp_endpoint: str | None) -> str | None:
    """Run the app's optional ``snapshot()`` hook; ``None`` when the app has none (or saw no state)."""
    hook = getattr(app, "snapshot", None)
    if hook is None:
        return None
    return await hook(cdp_endpoint)


__all__ = ["BenchmarkApp", "UIState", "prepare_app", "snapshot_app"]
