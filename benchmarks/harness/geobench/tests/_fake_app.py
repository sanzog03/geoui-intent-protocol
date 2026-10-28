"""A tiny application for harness tests: URLs are ``fake://?layers=a,b&t=YYYY-MM-DD``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models.test import TestModel

from geobench.app import UIState
from geoui import GeoIntent, LayerRef, TimeWindow


class FakeOutput(BaseModel):
    result: str
    url: str


class FakeApp:
    name = "fake"
    agent_kinds = ("x", "y")
    auto_layers = frozenset({"Base"})
    discovery_tools = frozenset({"search"})

    def __init__(self, agent_factory: Any = None):
        self.agent_factory = agent_factory
        self.built: list[str] = []

    def build_agent(self, kind: str, *, cdp_endpoint, extra_capabilities: Sequence[AbstractCapability]) -> Agent:
        self.built.append(kind)
        if self.agent_factory is not None:
            return self.agent_factory(kind, extra_capabilities)
        return Agent(TestModel(custom_output_text="ok"), name=f"fake_{kind}", capabilities=list(extra_capabilities))

    def chatbot_role(self, kind: str) -> str:
        return f"A fake {kind} assistant."

    def output_url(self, output: Any) -> str | None:
        return getattr(output, "url", None) or None

    def observe(self, url: str) -> UIState:
        parts = urlparse(url)
        if parts.scheme != "fake":
            raise ValueError(f"not a fake url: {url}")
        qs = parse_qs(parts.query)
        layers = [LayerRef(id=x) for x in qs.get("layers", [""])[0].split(",") if x]
        t = qs.get("t", [None])[0]
        return GeoIntent(layers=layers, time=TimeWindow(instant=t) if t else None)


def fake_url(*layers: str, t: str | None = None) -> str:
    url = "fake://app/?layers=" + ",".join(layers)
    return url + (f"&t={t}" if t else "")
