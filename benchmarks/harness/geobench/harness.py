"""The simulator's ``model_callback``: one agent, many conversations, every turn traced.

``ConversationRunner`` is what deepeval's ``ConversationSimulator`` calls for
each simulated user turn. It builds the application's agent lazily (inside
the simulator's event loop, with the tracing capability), keeps a
``message_history`` per conversation (``thread_id``), resets the shared
browser tab when a new conversation starts, runs the turn through
:func:`geobench.tracing.traced_turn`, writes the ``TurnRecord`` /
``ErrorRecord`` rows and the ``TurnTrace`` under the run directory, and
returns an assistant ``Turn`` whose metadata carries the evidence the
metrics read. Errors never reach the simulator: an error turn is recorded
and the conversation goes on (the stopping rule decides).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from deepeval.test_case import ConversationalTestCase, ToolCall, Turn
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from geobench.app import BenchmarkApp
from geobench.records import (
    ErrorRecord,
    OutputKind,
    Source,
    TurnRecord,
    append_record,
    default_trace_relpath,
    format_traceback,
    underlying_cause_summary,
    usage_from_run_usage,
)
from geobench.tracing import TracedRun, TurnTrace, save_trace, traced_turn, tracing_capability

log = logging.getLogger(__name__)

#: Per-turn request cap handed to pydantic-ai (runaway protection); same as the notebook.
DEFAULT_REQUEST_LIMIT = 50
#: OpenAI HTTP timeout per request; large VLM payloads need headroom (same as the notebook).
DEFAULT_MODEL_TIMEOUT_S = 900.0


# --- browser reset over the CDP HTTP API ----------------------------------


async def reset_browser_tab(cdp_endpoint: str, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Open a fresh ``about:blank`` tab and close every other page, so a conversation starts clean.

    Order matters: the new tab is opened first, because closing the last tab
    can end the browser process. Returns the new target id.
    """
    async with httpx.AsyncClient(base_url=cdp_endpoint, timeout=10.0, transport=transport) as client:
        created = (await client.put("/json/new?about:blank")).raise_for_status().json()
        new_id = created["id"]
        targets = (await client.get("/json/list")).raise_for_status().json()
        for target in targets:
            if target.get("type") == "page" and target.get("id") != new_id:
                await client.get(f"/json/close/{target['id']}")
        return new_id


# --- output classification -------------------------------------------------


def output_text(output: Any) -> str:
    """The assistant's visible reply: ``result`` for structured outputs, ``content`` for text."""
    for attr in ("result", "content"):
        value = getattr(output, attr, None)
        if isinstance(value, str):
            return value
    return str(output)


def classify_output(app: BenchmarkApp, run: TracedRun) -> tuple[OutputKind, str | None, str]:
    """``(output_kind, final_url, content)`` exactly as the notebook classifies a turn."""
    if run.error is not None:
        return "error", None, f"[{type(run.error).__name__}] {run.error}"
    output = run.result.output
    url = app.output_url(output)
    if url is None:
        return "text", None, output_text(output)
    return "structured", url, output_text(output)


# --- the runner -------------------------------------------------------------


class ConversationRunner:
    """deepeval ``model_callback`` for one agent kind of one application."""

    def __init__(
        self,
        app: BenchmarkApp,
        kind: str,
        *,
        run_dir: Path,
        cdp_endpoint: str | None,
        dataset: str,
        run_name: str,
        source: Source = "simulated",
        request_limit: int = DEFAULT_REQUEST_LIMIT,
        model_timeout_s: float = DEFAULT_MODEL_TIMEOUT_S,
        reset_browser: Callable[[str], Any] | None = reset_browser_tab,
        agent: Agent[Any, Any] | None = None,
    ) -> None:
        if kind not in app.agent_kinds:
            raise ValueError(f"unknown agent kind {kind!r}; expected one of {app.agent_kinds}")
        self.app = app
        self.kind = kind
        self.run_dir = Path(run_dir)
        self.cdp_endpoint = cdp_endpoint
        self.dataset = dataset
        self.run_name = run_name
        self.source: Source = source
        self.request_limit = request_limit
        self.model_timeout_s = model_timeout_s
        self._reset_browser = reset_browser
        self._agent = agent
        self._history: dict[str, list[Any]] = {}
        self._turn_index: dict[str, int] = {}
        self.golden_name: str | None = None
        self.browser_resets = 0

    # -- lifecycle -------------------------------------------------------

    def ensure_agent(self) -> Agent[Any, Any]:
        """Build the agent on first use (inside the running loop) with the tracing capability."""
        if self._agent is None:
            self._agent = self.app.build_agent(
                self.kind, cdp_endpoint=self.cdp_endpoint, extra_capabilities=[tracing_capability()]
            )
        return self._agent

    def start_golden(self, golden_name: str) -> None:
        """Tell the runner which golden the next conversation(s) belong to (the simulator does not pass it)."""
        self.golden_name = golden_name

    def history(self, thread_id: str) -> list[Any]:
        return list(self._history.get(thread_id, []))

    # -- the callback ----------------------------------------------------

    async def __call__(self, input: str, turns: list[Turn], thread_id: str) -> Turn:
        agent = self.ensure_agent()
        if thread_id not in self._history:
            self._history[thread_id] = []
            self._turn_index[thread_id] = 0
            await self._reset_for_new_conversation()
        self._turn_index[thread_id] += 1
        turn_index = self._turn_index[thread_id]

        run = await traced_turn(
            agent,
            input,
            message_history=self.history(thread_id),
            thread_id=thread_id,
            source=self.source,
            usage_limits=UsageLimits(request_limit=self.request_limit),
            model_settings={"timeout": self.model_timeout_s},
        )
        trace_rel = default_trace_relpath(thread_id, turn_index)
        save_trace(run.trace, self.run_dir / trace_rel)
        output_kind, final_url, content = classify_output(self.app, run)
        usage = usage_from_run_usage(run.result.usage) if run.result is not None else None
        tool_names = run.trace.tool_names

        record = TurnRecord(
            agent=self.kind,
            session_id=thread_id,
            run_id=run.trace.trace_id,
            turn_index=turn_index,
            user_prompt=input,
            tool_calls=tool_names,
            tool_call_count=len(tool_names),
            wall_clock_s=round(run.trace.duration_s, 3),
            usage=usage,
            output_kind=output_kind,
            final_url=final_url,
            error_type=type(run.error).__name__ if run.error is not None else None,
            error_message=str(run.error)[:500] if run.error is not None else None,
            source=self.source,
            run_name=self.run_name,
            dataset=self.dataset,
            golden_name=self.golden_name,
            trace_path=trace_rel,
        )
        append_record(record, self.run_dir / "turns.jsonl")
        if run.error is not None:
            append_record(
                ErrorRecord(
                    agent=self.kind,
                    session_id=thread_id,
                    turn_index=turn_index,
                    user_prompt=input,
                    error_type=type(run.error).__name__,
                    error_message=str(run.error),
                    underlying_cause=underlying_cause_summary(run.error),
                    traceback=format_traceback(run.error),
                    tool_calls=tool_names,
                    tool_call_count=len(tool_names),
                    wall_clock_s=round(run.trace.duration_s, 3),
                    source=self.source,
                    run_name=self.run_name,
                    dataset=self.dataset,
                    golden_name=self.golden_name,
                ),
                self.run_dir / "errors.jsonl",
            )
            log.warning("turn %s of %s errored: %s", turn_index, thread_id, record.error_message)
        else:
            self._history[thread_id] = run.result.all_messages()

        return Turn(
            role="assistant",
            content=content,
            tools_called=[
                ToolCall(name=t.name, input_parameters=t.args, output=t.output) for t in run.trace.tool_calls
            ],
            metadata=turn_metadata(record, run.trace),
        )

    async def _reset_for_new_conversation(self) -> None:
        if self._reset_browser is None or not self.cdp_endpoint:
            return
        try:
            await self._reset_browser(self.cdp_endpoint)
            self.browser_resets += 1
        except Exception as exc:  # noqa: BLE001 — a failed reset is logged, not fatal: the agent navigates anyway
            log.warning("browser reset failed (%s); continuing with the current tab", exc)


def turn_metadata(record: TurnRecord, trace: TurnTrace) -> dict[str, Any]:
    """The evidence an assistant ``Turn`` carries for the metrics (``trace`` inline, plus the row's facts)."""
    return {
        "turn_index": record.turn_index,
        "output_kind": record.output_kind,
        "final_url": record.final_url,
        "wall_clock_s": record.wall_clock_s,
        "usage": record.usage.model_dump() if record.usage else None,
        "tool_call_count": record.tool_call_count,
        "error_type": record.error_type,
        "trace_path": record.trace_path,
        "trace": trace.model_dump(mode="json"),
        "agent_kind": record.agent,
        "golden_name": record.golden_name,
    }


# --- transcripts --------------------------------------------------------------


class ConversationRecord(BaseModel):
    """One simulated conversation as committed in ``conversations.jsonl`` (traces by path, not inline)."""

    name: str
    agent: str
    dataset: str
    run_name: str
    golden_name: str
    session_id: str | None
    scenario: str | None
    expected_outcome: str | None
    chatbot_role: str | None
    turns: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)
    metrics: list[dict[str, Any]] = Field(default_factory=list)


def conversation_record(
    test_case: ConversationalTestCase,
    *,
    agent: str,
    dataset: str,
    run_name: str,
    golden_name: str,
    metrics: list[dict[str, Any]] | None = None,
) -> ConversationRecord:
    turns: list[dict[str, Any]] = []
    session_id: str | None = None
    for turn in test_case.turns:
        meta = dict(turn.metadata or {})
        trace = meta.pop("trace", None)
        if trace and session_id is None:
            session_id = trace.get("thread_id")
        turns.append(
            {
                "role": turn.role,
                "content": turn.content,
                "tools_called": [t.model_dump(mode="json") for t in (turn.tools_called or [])],
                "metadata": meta or None,
            }
        )
    metadata = {k: v for k, v in (test_case.metadata or {}).items() if k != "Persona"}
    return ConversationRecord(
        name=test_case.name or golden_name,
        agent=agent,
        dataset=dataset,
        run_name=run_name,
        golden_name=golden_name,
        session_id=session_id,
        scenario=test_case.scenario,
        expected_outcome=test_case.expected_outcome,
        chatbot_role=test_case.chatbot_role,
        turns=turns,
        metadata=metadata,
        metrics=metrics or [],
    )


__all__ = [
    "DEFAULT_MODEL_TIMEOUT_S",
    "DEFAULT_REQUEST_LIMIT",
    "ConversationRecord",
    "ConversationRunner",
    "classify_output",
    "conversation_record",
    "output_text",
    "reset_browser_tab",
    "turn_metadata",
]
