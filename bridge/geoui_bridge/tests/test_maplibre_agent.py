"""The MapLibre agent: wiring, prompt, and one scripted conversation through the fake page."""

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from geoui_bridge.agents import (
    AGENT_NAME,
    SYSTEM_PROMPT,
    MaplibreAgentOutput,
    build_maplibre_agent,
    maplibre_config,
)
from geoui_bridge.cdp import BridgeConfig

from ._fake_session import FakeSession

TOOL_NAMES = ["geo_ui_render_intent_tool", "geo_ui_get_state_tool", "geo_ui_list_intent_extensions_tool"]


@pytest.fixture(autouse=True)
def _dummy_openai_key(monkeypatch):
    """The OpenAI provider wants a key when the Agent is built; no request is ever sent here."""
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")


def test_config_prefers_arguments_over_environment():
    env = {"PLAYWRIGHT_CDP_ENDPOINT": "http://127.0.0.1:9333", "GEOUI_APP_URL": "http://localhost:5173"}
    assert maplibre_config(environ=env) == BridgeConfig(
        cdp_endpoint="http://127.0.0.1:9333", app_url="http://localhost:5173"
    )
    assert maplibre_config(cdp_endpoint="http://localhost:9222", environ=env).cdp_endpoint == "http://localhost:9222"
    assert maplibre_config(app_url="http://x:1", environ=env).app_url == "http://x:1"


def test_wiring_and_prompt():
    agent = build_maplibre_agent(session_factory=FakeSession().factory(), environ={})
    assert agent.name == AGENT_NAME
    assert agent.output_type == [MaplibreAgentOutput, str]  # plain text allowed: no forced tool choice
    for name in TOOL_NAMES:
        assert name in SYSTEM_PROMPT
    assert "REPLACES" in SYSTEM_PROMPT and "geoui_extensions" in SYSTEM_PROMPT


async def test_scripted_conversation_renders_through_the_page():
    page = FakeSession()
    agent = build_maplibre_agent(session_factory=page.factory(), environ={}, thinking=False)

    def scripted(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        done = [p.tool_name for m in messages for p in m.parts if p.part_kind == "tool-return"]
        if "geo_ui_list_intent_extensions_tool" not in done:
            return ModelResponse(parts=[ToolCallPart("geo_ui_list_intent_extensions_tool", {})])
        if "geo_ui_render_intent_tool" not in done:
            intent = {
                "viewport": {"bbox": [-125, 32, -114, 42]},
                "time": {"instant": "2025-09-15"},
                "layers": [{"id": "A"}],
            }
            return ModelResponse(parts=[ToolCallPart("geo_ui_render_intent_tool", {"intent": intent})])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "final_result", {"result": "Showing Layer A on 2025-09-15 over California."}
                )
            ]
        )

    result = await agent.run("Show layer A over California on 2025-09-15.", model=FunctionModel(scripted))
    assert isinstance(result.output, MaplibreAgentOutput) and "Layer A" in result.output.result
    assert [name for name, _ in page.calls] == [
        "describe",
        "describe",
        "render",
    ]  # list, then render's own catalogue check
    assert page.state["layers"] == [{"id": "A", "visible": True, "opacity": None}] and page.state["time"] == {
        "instant": "2025-09-15"
    }


async def test_a_back_to_back_repeat_of_the_list_call_gets_a_note_not_the_catalogue():
    """The loop seen live: the model re-issues the catalogue call right after receiving it."""
    page = FakeSession()
    agent = build_maplibre_agent(session_factory=page.factory(), environ={}, thinking=False)
    returns: list[int] = []

    def scripted(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        for m in messages:
            for p in m.parts:
                if p.part_kind == "tool-return" and p.tool_name == "geo_ui_list_intent_extensions_tool":
                    returns.append(len(str(p.content)))
        lists = sum(
            1
            for m in messages
            for p in m.parts
            if p.part_kind == "tool-call" and p.tool_name == "geo_ui_list_intent_extensions_tool"
        )
        if lists < 3:
            return ModelResponse(parts=[ToolCallPart("geo_ui_list_intent_extensions_tool", {})])
        return ModelResponse(parts=[TextPart("compare and raster-styling")])

    result = await agent.run("what do you support?", model=FunctionModel(scripted))
    assert result.output == "compare and raster-styling"
    assert page.calls == [("describe", None)]  # the page was asked once
    seen = sorted(set(returns))
    assert len(seen) == 2 and seen[0] < 400 < seen[1]  # one full catalogue, then the short note
