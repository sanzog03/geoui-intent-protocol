"""Per-turn JSONL records: the same fields the demo notebook logs, plus the run context.

``TurnRecord`` is a superset of ``worldview.agents.benchmark.log.TurnRecord``
(the notebook's row), so an analysis written for the manual logs reads a
benchmark run unchanged. The extra fields say which run, dataset and
golden a turn belongs to and where its trace was saved. ``session_id`` is
the conversation id.
"""

from __future__ import annotations

import os
import traceback as _traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

OutputKind = Literal["structured", "text", "error"]
Source = Literal["simulated", "manual"]


def new_session_id() -> str:
    """A short conversation id (uuid4 hex, 12 chars)."""
    return uuid.uuid4().hex[:12]


class TurnUsage(BaseModel):
    """Token / request counts for one turn. ``None`` means the source did not report it."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    requests: int | None = None
    cache_read_tokens: int | None = None
    reasoning_tokens: int | None = None
    tool_calls: int | None = None
    cost_usd: float | None = None

    @property
    def cache_adjusted_tokens(self) -> int | None:
        """prompts.md's effective cost: input − cache_read + 0.1·cache_read + output."""
        if self.input_tokens is None or self.output_tokens is None:
            return None
        cached = self.cache_read_tokens or 0
        return round(self.input_tokens - cached + 0.1 * cached + self.output_tokens)


class TurnRecord(BaseModel):
    """One row per completed (or errored) agent turn."""

    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    agent: str
    session_id: str = Field(description="Conversation id; all turns of one conversation share it")
    run_id: str | None = None
    turn_index: int
    user_prompt: str
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_count: int = 0
    wall_clock_s: float
    usage: TurnUsage | None = None
    output_kind: OutputKind
    final_url: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    # --- benchmark context (absent in the notebook's rows) ---
    source: Source = "simulated"
    run_name: str | None = None
    dataset: str | None = None
    golden_name: str | None = None
    trace_path: str | None = Field(default=None, description="Path of the saved TurnTrace, relative to the run dir")


class ErrorRecord(BaseModel):
    """One row per errored turn: the full traceback and the deepest cause."""

    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    agent: str
    session_id: str
    turn_index: int
    retry_attempt: int = 0
    user_prompt: str
    error_type: str
    error_message: str
    underlying_cause: str | None = None
    traceback: str
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_count: int = 0
    wall_clock_s: float
    source: Source = "simulated"
    run_name: str | None = None
    dataset: str | None = None
    golden_name: str | None = None


def append_record(record: BaseModel, path: Path) -> Path:
    """Append one JSON line; create the parent directory on first use."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json(exclude_none=False) + "\n")
    return path


def load_records[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    """Read every non-blank line of a JSONL file as ``model``; a missing file is empty."""
    path = Path(path)
    if not path.exists():
        return []
    rows: list[T] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(model.model_validate_json(line))
    return rows


def usage_from_run_usage(usage: Any) -> TurnUsage | None:
    """Read a pydantic-ai ``RunUsage`` (2.x attribute layout) into :class:`TurnUsage`."""
    if usage is None:
        return None
    details = getattr(usage, "details", None) or {}
    total = getattr(usage, "total_tokens", None)
    cost = getattr(usage, "cost", None)
    return TurnUsage(
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        total_tokens=total() if callable(total) else total,
        requests=getattr(usage, "requests", None),
        cache_read_tokens=getattr(usage, "cache_read_tokens", None),
        reasoning_tokens=getattr(usage, "output_reasoning_tokens", None) or details.get("reasoning_tokens"),
        tool_calls=getattr(usage, "tool_calls", None),
        cost_usd=float(cost) if cost is not None else None,
    )


# --- exception helpers (ported from demo/chat.py, which keeps its own copies) ---


def flatten_exceptions(exc: BaseException) -> list[BaseException]:
    """Recursively flatten an ``ExceptionGroup`` into its leaf exceptions."""
    if isinstance(exc, BaseExceptionGroup):
        leaves: list[BaseException] = []
        for sub in exc.exceptions:
            leaves.extend(flatten_exceptions(sub))
        return leaves
    return [exc]


def deepest_in_chain(exc: BaseException) -> BaseException:
    """Follow ``__cause__`` / ``__context__`` to the root exception."""
    seen: set[int] = set()
    current = exc
    while id(current) not in seen:
        seen.add(id(current))
        nxt = current.__cause__ or current.__context__
        if nxt is None:
            break
        current = nxt
    return current


def underlying_cause_summary(exc: BaseException) -> str | None:
    """``"ClassName: message"`` of the deepest cause, or ``None`` when there is no chain."""
    leaves = flatten_exceptions(exc)
    leaf = leaves[0] if leaves else exc
    root = deepest_in_chain(leaf)
    if root is leaf and leaf is exc:
        return None
    return f"{type(root).__name__}: {root}"


def format_traceback(exc: BaseException) -> str:
    return "".join(_traceback.format_exception(type(exc), exc, exc.__traceback__))


def scrub_paths(text: str, replacements: dict[str, str] | None = None) -> str:
    """Replace machine-specific absolute paths so committed results carry none.

    By default the current working directory becomes ``<repo>`` and the
    interpreter prefix ``<python>``; home directories of the form
    ``/Users/<name>`` and ``/home/<name>`` become ``<home>``.
    """
    import re
    import sys

    replacements = replacements or {str(Path.cwd()): "<repo>", sys.prefix: "<python>", sys.base_prefix: "<python>"}
    for src, dst in sorted(replacements.items(), key=lambda kv: -len(kv[0])):
        if src:
            text = text.replace(src, dst)
    text = re.sub(r"/(?:Users|home)/[^/\s\"']+", "<home>", text)
    return text


def default_trace_relpath(session_id: str, turn_index: int) -> str:
    return os.path.join("traces", session_id, f"{turn_index:02d}.json")


__all__ = [
    "ErrorRecord",
    "OutputKind",
    "Source",
    "TurnRecord",
    "TurnUsage",
    "append_record",
    "deepest_in_chain",
    "default_trace_relpath",
    "flatten_exceptions",
    "format_traceback",
    "load_records",
    "new_session_id",
    "scrub_paths",
    "underlying_cause_summary",
    "usage_from_run_usage",
]
