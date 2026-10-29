"""The runner drives an offline TestModel agent exactly as the simulator would."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from deepeval.test_case import ConversationalTestCase, Turn
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from geouibench.harness import (
    ConversationRunner,
    classify_output,
    conversation_record,
    output_text,
    reset_browser_tab,
)
from geouibench.metrics import SuccessMetric, ToolEfficiencyMetric, trace_of
from geouibench.records import ErrorRecord, TurnRecord, load_records
from geouibench.tests._fake_app import FakeApp, FakeOutput, fake_url
from geouibench.tracing import load_trace


def _structured_agent(kind, caps):
    tools = FunctionToolset(id="t")

    @tools.tool_plain
    def lookup(q: str) -> str:
        """Look something up."""
        return "found " + q

    model = TestModel(custom_output_args={"result": "rendered", "url": fake_url("A", t="2025-09-15")})
    return Agent(model, name=f"agent_{kind}", output_type=FakeOutput, toolsets=[tools], capabilities=list(caps))


def _text_agent(kind, caps):
    return Agent(TestModel(custom_output_text="which layer?"), name=f"text_{kind}", capabilities=list(caps))


def _failing_agent(kind, caps):
    tools = FunctionToolset(id="t")

    @tools.tool_plain
    def boom() -> str:
        """Fails."""
        raise RuntimeError("tool exploded")

    return Agent(TestModel(), name=f"fail_{kind}", toolsets=[tools], capabilities=list(caps), retries=0)


class _Resets:
    def __init__(self):
        self.calls: list[str] = []

    async def __call__(self, endpoint: str):
        self.calls.append(endpoint)


def _runner(tmp_path, factory, **kw) -> tuple[ConversationRunner, _Resets]:
    resets = _Resets()
    runner = ConversationRunner(
        FakeApp(factory),
        "x",
        run_dir=tmp_path / "run",
        cdp_endpoint="http://cdp:9222",
        dataset="gold",
        run_name="r1",
        reset_browser=resets,
        **kw,
    )
    return runner, resets


def test_structured_turns_build_history_write_rows_and_traces(tmp_path):
    runner, resets = _runner(tmp_path, _structured_agent)
    runner.start_golden("g1")

    async def go():
        t1 = await runner("render A", [Turn(role="user", content="render A")], "thread-1")
        t2 = await runner("now zoom", [], "thread-1")
        t3 = await runner("other conv", [], "thread-2")
        return t1, t2, t3

    t1, t2, t3 = asyncio.run(go())
    assert runner.app.built == ["x"]  # built once, lazily
    assert resets.calls == ["http://cdp:9222", "http://cdp:9222"]  # once per conversation
    assert t1.role == "assistant" and t1.content == "rendered"
    assert t1.metadata["output_kind"] == "structured" and t1.metadata["final_url"] == fake_url("A", t="2025-09-15")
    assert t1.metadata["turn_index"] == 1 and t2.metadata["turn_index"] == 2 and t3.metadata["turn_index"] == 1
    assert [t.name for t in t1.tools_called] == ["lookup"] and t1.tools_called[0].input_parameters == {"q": "a"}
    assert trace_of(t1).tool_names == ["lookup"]
    assert len(runner.history("thread-1")) > len(runner.history("thread-2")) > 0

    rows = load_records(tmp_path / "run" / "turns.jsonl", TurnRecord)
    assert [(r.session_id, r.turn_index, r.golden_name, r.dataset, r.run_name) for r in rows] == [
        ("thread-1", 1, "g1", "gold", "r1"),
        ("thread-1", 2, "g1", "gold", "r1"),
        ("thread-2", 1, "g1", "gold", "r1"),
    ]
    assert rows[0].usage.requests == 2 and rows[0].tool_calls == ["lookup"] and rows[0].wall_clock_s > 0
    assert rows[0].trace_path == "traces/thread-1/01.json"
    saved = load_trace(tmp_path / "run" / rows[0].trace_path)
    assert saved.thread_id == "thread-1" and saved.tool_names == ["lookup"]
    assert not (tmp_path / "run" / "errors.jsonl").exists()

    # the metrics can read the returned turns directly
    tc = ConversationalTestCase(
        turns=[Turn(role="user", content="render A"), t1],
        metadata={
            "expected_state": {"layers": {"A": None}, "time": "2025-09-15"},
            "budgets": {"seconds_per_turn": 5, "tokens_per_turn": 100},
        },
    )
    assert SuccessMetric(runner.app).measure(tc) == 1.0
    assert ToolEfficiencyMetric(runner.app).measure(tc) == 1.0


def test_consecutive_turns_in_one_loop_get_separate_traces(tmp_path):
    """The simulator calls the callback repeatedly on one event loop; each turn must get its own trace.

    Before the fix, deepeval's trace context leaked between calls and turn N's trace held the
    spans of turns 1..N (turn 3 would show three tool calls and six LLM calls).
    """
    runner, _ = _runner(tmp_path, _structured_agent)

    async def go():
        fresh = [await runner.respond("render", [], f"conv-{i}") for i in range(3)]
        again = await runner.respond("now zoom", [], "conv-0")  # with history: TestModel answers without a tool
        return fresh, again

    fresh, again = asyncio.run(go())
    for turn in fresh:
        assert trace_of(turn).tool_names == ["lookup"]
        assert len(trace_of(turn).llm_calls) == 2
    assert len({trace_of(t).trace_id for t in fresh}) == 3
    assert trace_of(again).tool_names == [] and len(trace_of(again).llm_calls) == 1
    assert trace_of(again).trace_id not in {trace_of(t).trace_id for t in fresh}


def test_text_turn_is_classified_as_text(tmp_path):
    runner, _ = _runner(tmp_path, _text_agent)
    turn = asyncio.run(runner("hi", [], "t"))
    assert turn.content == "which layer?" and turn.metadata["output_kind"] == "text"
    assert turn.metadata["final_url"] is None and turn.tools_called == []


def test_error_turn_is_recorded_and_history_is_unchanged(tmp_path):
    runner, _ = _runner(tmp_path, _failing_agent)
    runner.start_golden("g2")
    turn = asyncio.run(runner("go", [], "t"))
    assert turn.metadata["output_kind"] == "error" and "tool exploded" in turn.content
    assert runner.history("t") == []
    rows = load_records(tmp_path / "run" / "turns.jsonl", TurnRecord)
    assert rows[0].output_kind == "error" and rows[0].error_type == "RuntimeError"
    assert rows[0].usage is not None and rows[0].usage.requests == 1 and rows[0].usage.input_tokens > 0
    errors = load_records(tmp_path / "run" / "errors.jsonl", ErrorRecord)
    assert len(errors) == 1 and "tool exploded" in errors[0].traceback and errors[0].golden_name == "g2"
    assert (tmp_path / "run" / "traces" / "t" / "01.json").exists()


def test_a_failed_browser_reset_does_not_fail_the_turn(tmp_path):
    async def broken(endpoint):
        raise ConnectionError("no browser")

    runner = ConversationRunner(
        FakeApp(_text_agent),
        "x",
        run_dir=tmp_path,
        cdp_endpoint="http://x",
        dataset="d",
        run_name="r",
        reset_browser=broken,
    )
    turn = asyncio.run(runner("hi", [], "t"))
    assert turn.metadata["output_kind"] == "text" and runner.browser_resets == 0


def test_no_cdp_endpoint_means_no_reset(tmp_path):
    resets = _Resets()
    runner = ConversationRunner(
        FakeApp(_text_agent), "x", run_dir=tmp_path, cdp_endpoint=None, dataset="d", run_name="r", reset_browser=resets
    )
    asyncio.run(runner("hi", [], "t"))
    assert resets.calls == []


def test_respond_is_what_deepeval_sees_as_an_async_callback(tmp_path):
    import inspect

    runner, _ = _runner(tmp_path, _text_agent)
    assert inspect.iscoroutinefunction(runner.respond)
    assert not inspect.iscoroutinefunction(runner)  # the instance itself would be treated as sync by deepeval
    assert set(inspect.signature(runner.respond).parameters) == {"input", "turns", "thread_id"}


def test_unknown_kind_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        ConversationRunner(FakeApp(), "nope", run_dir=tmp_path, cdp_endpoint=None, dataset="d", run_name="r")


def test_reset_browser_tab_opens_new_then_closes_others():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}?{request.url.query.decode()}")
        if request.url.path == "/json/new":
            return httpx.Response(200, json={"id": "NEW", "type": "page"})
        if request.url.path == "/json/list":
            return httpx.Response(
                200,
                json=[
                    {"id": "OLD1", "type": "page"},
                    {"id": "NEW", "type": "page"},
                    {"id": "W", "type": "service_worker"},
                ],
            )
        return httpx.Response(200, text="Target is closing")

    new_id = asyncio.run(reset_browser_tab("http://cdp:9222", transport=httpx.MockTransport(handler)))
    assert new_id == "NEW"
    assert seen == ["PUT /json/new?about:blank", "GET /json/list?", "GET /json/close/OLD1?"]


def test_snapshot_fills_the_handle_for_page_state_apps(tmp_path):
    """An app whose state is not in a URL returns None from output_url and a handle from snapshot()."""

    class SnapshotApp(FakeApp):
        def __init__(self):
            super().__init__(_text_agent)
            self.snapshots: list[str | None] = []

        def output_url(self, output):
            return None

        async def snapshot(self, cdp_endpoint):
            self.snapshots.append(cdp_endpoint)
            return fake_url("A", t="2025-09-15")

    app = SnapshotApp()
    runner = ConversationRunner(
        app,
        "x",
        run_dir=tmp_path / "run",
        cdp_endpoint="http://cdp:9222",
        dataset="gold",
        run_name="r1",
        reset_browser=None,
    )
    runner.start_golden("g1")
    turn = asyncio.run(runner("render A", [], "t"))
    assert app.snapshots == ["http://cdp:9222"]
    assert turn.metadata["output_kind"] == "text" and turn.metadata["final_url"] == fake_url("A", t="2025-09-15")
    rows = load_records(tmp_path / "run" / "turns.jsonl", TurnRecord)
    assert rows[0].final_url == fake_url("A", t="2025-09-15")
    tc = ConversationalTestCase(
        turns=[Turn(role="user", content="render A"), turn],
        metadata={"expected_state": {"layers": {"A": None}, "time": "2025-09-15"}},
    )
    assert SuccessMetric(app).measure(tc) == 1.0  # judged from the snapshot handle, offline


def test_classify_and_output_text():
    assert output_text(FakeOutput(result="r", url="u")) == "r"
    assert output_text("plain") == "plain"

    class ResultOnly(BaseModel):
        result: str

    class _ResultRun:
        error = None

        class result:
            output = ResultOnly(result="shown")

    assert classify_output(FakeApp(), _ResultRun()) == ("structured", None, "shown")

    class _Run:
        error = None

        class result:
            output = FakeOutput(result="r", url=fake_url("A"))

    kind, url, content = classify_output(FakeApp(), _Run())
    assert (kind, url, content) == ("structured", fake_url("A"), "r")


def test_conversation_record_strips_inline_traces(tmp_path):
    runner, _ = _runner(tmp_path, _structured_agent)
    turn = asyncio.run(runner("render", [], "conv"))
    tc = ConversationalTestCase(
        turns=[Turn(role="user", content="render"), turn],
        scenario="s",
        expected_outcome="e",
        chatbot_role="role",
        name="g[x]",
        metadata={"Persona": "p", "agent_kind": "x"},
    )
    rec = conversation_record(tc, agent="x", dataset="gold", run_name="r1", golden_name="g")
    assert rec.session_id == "conv" and rec.name == "g[x]" and rec.metadata == {"agent_kind": "x"}
    assert rec.turns[1]["metadata"]["trace_path"] == "traces/conv/01.json"
    assert "trace" not in rec.turns[1]["metadata"]
    assert rec.turns[1]["tools_called"][0]["name"] == "lookup"
    json.loads(rec.model_dump_json())  # serialisable as one JSONL line
