"""The app seam is a runtime-checkable Protocol: a minimal object satisfies it."""

import asyncio

from geouibench import BenchmarkApp
from geouibench.app import prepare_app, snapshot_app
from geouibench.datasets import Budgets


class _MinimalApp:
    name = "minimal"
    agent_kinds = ("a",)
    auto_layers = frozenset()
    discovery_tools = frozenset()
    budgets = Budgets(seconds_per_turn=1, tokens_per_turn=1)

    def build_agent(self, kind, *, cdp_endpoint, extra_capabilities):
        raise NotImplementedError

    def chatbot_role(self, kind):
        return "role"

    def output_url(self, output):
        return None

    def observe(self, url):
        raise ValueError(url)


def test_minimal_object_satisfies_protocol():
    assert isinstance(_MinimalApp(), BenchmarkApp)


def test_object_missing_a_member_does_not():
    class Half:
        name = "half"

    assert not isinstance(Half(), BenchmarkApp)


def test_prepare_hook_is_optional():
    assert prepare_app(_MinimalApp()) == {}

    class WithPrepare(_MinimalApp):
        def prepare(self):
            return {"X": "1"}

    assert prepare_app(WithPrepare()) == {"X": "1"}


def test_snapshot_hook_is_optional():
    assert asyncio.run(snapshot_app(_MinimalApp(), None)) is None

    class WithSnapshot(_MinimalApp):
        async def snapshot(self, cdp_endpoint):
            return f"state@{cdp_endpoint}"

    assert asyncio.run(snapshot_app(WithSnapshot(), "http://cdp:9222")) == "state@http://cdp:9222"
