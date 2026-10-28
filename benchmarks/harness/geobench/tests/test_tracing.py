"""Tracing captures LLM and tool spans from a real (offline) pydantic-ai run."""

import asyncio
import os
from datetime import UTC, datetime
from time import perf_counter

from deepeval.tracing.types import BaseSpan, LlmSpan, ToolSpan, Trace, TraceSpanStatus
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from geobench.tracing import (
    TurnTrace,
    load_trace,
    save_trace,
    traced_turn,
    tracing_capability,
    turn_trace_from_deepeval,
)

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")


def _agent() -> Agent:
    tools = FunctionToolset(id="t")

    @tools.tool_plain
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    return Agent(TestModel(), name="offline_agent", toolsets=[tools], capabilities=[tracing_capability()])


def test_traced_turn_captures_llm_and_tool_spans(tmp_path):
    agent = _agent()
    run = asyncio.run(traced_turn(agent, "add 1 and 2", message_history=None, thread_id="th-1"))
    assert run.error is None and run.result is not None
    trace = run.trace
    assert isinstance(trace, TurnTrace)
    assert trace.thread_id == "th-1" and trace.source == "simulated"
    assert trace.duration_s > 0
    assert trace.tool_names == ["add"]
    assert trace.tool_calls[0].args == {"a": 0, "b": 0}  # TestModel's generated arguments
    assert trace.tool_calls[0].output == "0"
    assert len(trace.llm_calls) == 2  # one request that calls the tool, one final answer
    assert all(call.model for call in trace.llm_calls)
    assert trace.usage is not None and trace.usage.requests == 2
    # tokens on the spans match pydantic-ai's own count (TestModel estimates both the same way)
    assert trace.span_input_tokens == trace.usage.input_tokens
    assert trace.span_output_tokens == trace.usage.output_tokens

    path = save_trace(trace, tmp_path / "traces" / "th-1" / "01.json")
    assert load_trace(path) == trace


def test_traced_turn_returns_errors_with_a_partial_trace():
    tools = FunctionToolset(id="t")

    @tools.tool_plain
    def boom() -> str:
        """Always fails."""
        raise RuntimeError("tool exploded")

    agent = Agent(TestModel(), name="failing", toolsets=[tools], capabilities=[tracing_capability()], retries=0)
    run = asyncio.run(traced_turn(agent, "go", message_history=None, thread_id="th-2"))
    assert run.result is None and run.error is not None
    assert "tool exploded" in run.trace.error
    assert run.trace.llm_calls  # the request that chose the tool was still recorded


def test_mapping_filters_mcp_noise_and_keeps_outer_tool_span():
    t0 = perf_counter()
    outer = ToolSpan(
        uuid="o", trace_uuid="t", start_time=t0 + 1, end_time=t0 + 3, status=TraceSpanStatus.SUCCESS,
        name="browser_navigate", input={"url": "https://x"}, output="navigated", children=[
            ToolSpan(uuid="i", trace_uuid="t", start_time=t0 + 1, end_time=t0 + 3, status=TraceSpanStatus.SUCCESS,
                     name="browser_navigate")
        ],
    )  # fmt: skip
    llm = LlmSpan(
        uuid="l", trace_uuid="t", start_time=t0, end_time=t0 + 1, status=TraceSpanStatus.SUCCESS,
        model="gpt-5.2", input_token_count=100.0, output_token_count=10.0,
    )  # fmt: skip
    listing = BaseSpan(
        uuid="b", trace_uuid="t", start_time=t0, end_time=t0, status=TraceSpanStatus.SUCCESS, name="tools/list"
    )
    trace = Trace(uuid="t", root_spans=[listing, llm, outer], start_time=t0, status=TraceSpanStatus.SUCCESS)
    mapped = turn_trace_from_deepeval(
        trace, thread_id="x", source="simulated", started_at=datetime.now(UTC), turn_start=t0, duration_s=3.0
    )
    assert mapped.tool_names == ["browser_navigate"]
    assert mapped.tool_calls[0].args == {"url": "https://x"} and mapped.tool_calls[0].duration_s == 2.0
    assert mapped.other_spans == ["tools/list"]
    assert mapped.llm_calls[0].input_tokens == 100 and mapped.llm_calls[0].model == "gpt-5.2"
    assert mapped.usage is None
