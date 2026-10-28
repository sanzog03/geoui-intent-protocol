"""One deepeval trace per agent turn, captured in-process and saved as evidence.

The agent is instrumented with deepeval's pydantic-ai integration, a plain
pydantic-ai capability passed through the application's ``build_agent``
(no agent code changes). :func:`traced_turn` wraps one ``agent.run`` in a
deepeval ``@observe`` span, so the OpenTelemetry spans pydantic-ai emits
(agent, LLM requests, tool calls) are routed to deepeval's local trace
manager instead of the hosted service, and reads the finished trace back
before the span closes. :func:`turn_trace_from_deepeval` flattens it into
:class:`TurnTrace`, the app-agnostic record the efficiency metrics and the
offline scorer consume.

What the spike (2026-10-28, deepeval 4.3.2, pydantic-ai 2.63) established:
LLM spans carry input/output token counts per request (their sum equals
``result.usage``); cache-read and reasoning tokens are not on the spans, so
they come from ``result.usage`` and are recorded as such; tool spans carry
arguments and (truncated) results; MCP ``tools/list`` calls appear as
untyped spans and MCP tool calls appear twice (an outer typed span and an
inner duplicate with no input), which the mapping filters out.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from deepeval.integrations.pydantic_ai import DeepEvalInstrumentationSettings
from deepeval.tracing import observe, update_current_span, update_current_trace
from deepeval.tracing.context import current_trace_context
from deepeval.tracing.types import BaseSpan, LlmSpan, ToolSpan, Trace
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.capabilities import Instrumentation

from geobench.records import Source, TurnUsage, usage_from_run_usage

#: Tool outputs are kept to this many characters in the saved trace.
OUTPUT_LIMIT = 2000


_settings: DeepEvalInstrumentationSettings | None = None


def instrumentation_settings() -> DeepEvalInstrumentationSettings:
    """One deepeval OpenTelemetry pipeline per process (constructing it sets the global tracer provider)."""
    global _settings
    if _settings is None:
        _settings = DeepEvalInstrumentationSettings()
    return _settings


def tracing_capability() -> Instrumentation:
    """deepeval's pydantic-ai instrumentation as an agent capability."""
    return Instrumentation(settings=instrumentation_settings())


class LLMCall(BaseModel):
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_s: float
    offset_s: float = Field(description="Seconds after the turn started")
    error: str | None = None


class ToolCallRecord(BaseModel):
    name: str
    args: dict[str, Any] | None = None
    output: str | None = None
    duration_s: float
    offset_s: float
    error: str | None = None


class TurnTrace(BaseModel):
    """The evidence for one assistant turn, derived from its deepeval trace."""

    trace_id: str
    thread_id: str | None = None
    source: Source = "simulated"
    started_at: str
    duration_s: float
    llm_calls: list[LLMCall] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    other_spans: list[str] = Field(default_factory=list, description="Names of untyped spans (e.g. MCP tools/list)")
    error: str | None = None
    usage: TurnUsage | None = Field(default=None, description="pydantic-ai's RunUsage for the turn (cross-check)")
    usage_source: str = Field(
        default="pydantic_ai",
        description="Where cache_read / reasoning tokens come from; input/output tokens are on the spans",
    )

    @property
    def span_input_tokens(self) -> int:
        return sum(c.input_tokens or 0 for c in self.llm_calls)

    @property
    def span_output_tokens(self) -> int:
        return sum(c.output_tokens or 0 for c in self.llm_calls)

    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self.tool_calls]

    def usage_from_spans(self) -> TurnUsage:
        """Token counts summed over the LLM spans; the fallback for turns where the run raised and left no RunUsage."""
        return TurnUsage(
            input_tokens=self.span_input_tokens,
            output_tokens=self.span_output_tokens,
            total_tokens=self.span_input_tokens + self.span_output_tokens,
            requests=len(self.llm_calls),
            cache_read_tokens=self.usage.cache_read_tokens if self.usage else None,
            reasoning_tokens=self.usage.reasoning_tokens if self.usage else None,
            tool_calls=len(self.tool_calls),
            cost_usd=self.usage.cost_usd if self.usage else None,
        )


def _duration(span: BaseSpan) -> float:
    return max(0.0, (span.end_time or span.start_time) - span.start_time)


def _truncate(value: Any) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= OUTPUT_LIMIT else text[:OUTPUT_LIMIT] + "…"


def _walk(spans: Iterable[BaseSpan], *, parent: BaseSpan | None = None):
    for span in spans:
        yield span, parent
        yield from _walk(span.children, parent=span)


def turn_trace_from_deepeval(
    trace: Trace,
    *,
    thread_id: str | None,
    source: Source,
    started_at: datetime,
    turn_start: float,
    duration_s: float,
    usage: Any = None,
    error: str | None = None,
) -> TurnTrace:
    """Flatten a deepeval ``Trace`` into a :class:`TurnTrace`."""
    llm_calls: list[LLMCall] = []
    tool_calls: list[ToolCallRecord] = []
    other: list[str] = []
    for span, parent in _walk(trace.root_spans):
        offset = max(0.0, span.start_time - turn_start)
        if isinstance(span, LlmSpan):
            llm_calls.append(
                LLMCall(
                    model=span.model,
                    input_tokens=int(span.input_token_count) if span.input_token_count is not None else None,
                    output_tokens=int(span.output_token_count) if span.output_token_count is not None else None,
                    duration_s=_duration(span),
                    offset_s=offset,
                    error=span.error,
                )
            )
        elif isinstance(span, ToolSpan):
            # MCP tools show up twice: the outer typed span with args/result and an
            # inner duplicate of the same name with no input. Keep the outer one.
            if isinstance(parent, ToolSpan) and parent.name == span.name and span.input is None:
                continue
            args = span.input if isinstance(span.input, dict) else None
            tool_calls.append(
                ToolCallRecord(
                    name=span.name,
                    args=args,
                    output=_truncate(span.output),
                    duration_s=_duration(span),
                    offset_s=offset,
                    error=span.error,
                )
            )
        elif type(span) is BaseSpan and span.name:
            other.append(span.name)
    return TurnTrace(
        trace_id=trace.uuid,
        thread_id=thread_id,
        source=source,
        started_at=started_at.isoformat(),
        duration_s=duration_s,
        llm_calls=llm_calls,
        tool_calls=tool_calls,
        other_spans=other,
        error=error,
        usage=usage_from_run_usage(usage),
    )


class TracedRun(BaseModel):
    """What :func:`traced_turn` returns: the run's result (or the error) and its trace."""

    model_config = {"arbitrary_types_allowed": True}

    result: Any = None
    error: BaseException | None = None
    trace: TurnTrace


@observe(type="agent", name="turn")
async def traced_turn(
    agent: Agent[Any, Any],
    user_input: str,
    *,
    message_history: list[Any] | None,
    thread_id: str,
    source: Source = "simulated",
    **run_kwargs: Any,
) -> TracedRun:
    """Run one agent turn inside a deepeval trace and return the result with its :class:`TurnTrace`.

    Exceptions from the run are caught and returned in ``TracedRun.error``
    so the (partial) trace is still captured; the caller decides what an
    error turn means. The deepeval trace is never posted anywhere.
    """
    update_current_trace(thread_id=thread_id, metadata={"source": source})
    started_at = datetime.now(UTC)
    t0 = perf_counter()
    result: Any = None
    error: BaseException | None = None
    try:
        result = await agent.run(user_input, message_history=message_history, **run_kwargs)
    except BaseException as exc:  # noqa: BLE001 — recorded, not swallowed: it is returned to the caller
        error = exc
    duration = perf_counter() - t0
    update_current_span(input=user_input, output=str(result.output) if result is not None else f"error: {error!r}")

    trace = current_trace_context.get()
    if trace is None:  # pragma: no cover — only if observe() was bypassed
        raise RuntimeError("traced_turn must run inside a deepeval trace context")
    trace.drop = True  # local evidence only: never post to Confident AI
    turn_trace = turn_trace_from_deepeval(
        trace,
        thread_id=thread_id,
        source=source,
        started_at=started_at,
        turn_start=t0,
        duration_s=duration,
        usage=result.usage if result is not None else None,
        error=f"{type(error).__name__}: {error}" if error is not None else None,
    )
    return TracedRun(result=result, error=error, trace=turn_trace)


def save_trace(trace: TurnTrace, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_trace(path: Path) -> TurnTrace:
    return TurnTrace.model_validate_json(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "OUTPUT_LIMIT",
    "LLMCall",
    "ToolCallRecord",
    "TracedRun",
    "TurnTrace",
    "instrumentation_settings",
    "load_trace",
    "save_trace",
    "traced_turn",
    "tracing_capability",
    "turn_trace_from_deepeval",
]
