"""``python -m geouibench export <run dir>...``: flatten a run into CSV tables for charting.

Three tables, written to ``<run dir>/csv/`` (or, with ``--out``, one combined
set for several runs):

``conversations.csv``
    one row per golden × agent: the six metric scores and pass flags, a single
    ``correct`` flag (Success on gold goldens, Completion on synthetic ones),
    tool calls and the waste breakdown, LLM requests, wall clock, tokens, cost,
    the golden's budgets and caps, the final URL and the judges' reasons.
``turns.csv``
    one row per assistant turn: tools, wall clock, LLM and tool time, tokens, cost,
    output kind, URL, error.
``tool_calls.csv``
    one row per tool call: name, duration, offset into the turn, error, whether it
    repeats an earlier call of the conversation or is a discovery call on a fully
    specified prompt.

Scores come from ``conversations.jsonl`` (what deepeval recorded); the waste and
per-turn breakdowns are recomputed from the committed traces with the same
deterministic metric classes the scorer uses, so a row can always be traced back
to its evidence. Nothing here needs an agent, a browser or a network.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from geouibench.app import BenchmarkApp
from geouibench.datasets import GoldenMeta
from geouibench.harness import ConversationRecord
from geouibench.metrics import (
    CompletionMetric,
    SuccessMetric,
    TimeEfficiencyMetric,
    TokenEfficiencyMetric,
    ToolEfficiencyMetric,
)
from geouibench.records import TurnRecord, TurnUsage
from geouibench.run_dir import load_conversations, load_turns, read_run_info
from geouibench.score import app_for_run, rebuild_test_case
from geouibench.tracing import TurnTrace, load_trace

log = logging.getLogger(__name__)

CSV_DIR = "csv"
CONVERSATIONS_CSV = "conversations.csv"
TURNS_CSV = "turns.csv"
TOOL_CALLS_CSV = "tool_calls.csv"

#: Metric name → column prefix.
METRIC_COLUMNS = {
    "Success": "success",
    "Completion": "completion",
    "Tool efficiency": "tool_efficiency",
    "Time efficiency": "time_efficiency",
    "Token efficiency": "token_efficiency",
    "Turn Relevancy": "turn_relevancy",
}

CONVERSATION_FIELDS = [
    # identity
    "run",
    "app",
    "dataset",
    "golden_kind",
    "golden",
    "agent",
    "session_id",
    "conversation",
    # the golden's rules
    "fully_specified",
    "max_user_simulations",
    "state_threshold",
    "checkpoints",
    "budget_seconds_per_turn",
    "budget_tokens_per_turn",
    # outcome
    "correct",
    "correctness_basis",
    *[f"{p}_{s}" for p in METRIC_COLUMNS.values() for s in ("score", "pass")],
    "expected_fields",
    "matched_fields",
    "missed_fields",
    "checkpoints_reached",
    # shape of the conversation
    "user_turns",
    "assistant_turns",
    "error_turns",
    "first_url_turn",
    "final_url",
    "simulator_error",
    # tools
    "tool_calls",
    "distinct_tools",
    "wasted_tool_calls",
    "duplicate_tool_calls",
    "errored_tool_calls",
    "discovery_tool_calls",
    "tool_calls_by_name",
    # time
    "seconds",
    "mean_seconds_per_turn",
    "max_seconds_per_turn",
    "llm_seconds",
    "tool_seconds",
    "elapsed_seconds",
    "started_at",
    "ended_at",
    # tokens and money
    "llm_requests",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "reasoning_tokens",
    "total_tokens",
    "cache_adjusted_tokens",
    "mean_cache_adjusted_tokens_per_turn",
    "cost_usd",
    "cost_complete",
    # judges' words
    "success_reason",
    "completion_reason",
    "tool_efficiency_reason",
    "turn_relevancy_reason",
]

TURN_FIELDS = [
    "run",
    "app",
    "dataset",
    "golden_kind",
    "golden",
    "agent",
    "session_id",
    "turn_index",
    "timestamp",
    "output_kind",
    "has_url",
    "final_url",
    "error_type",
    "error_message",
    "tool_calls",
    "distinct_tools",
    "tool_names",
    "llm_requests",
    "wall_clock_s",
    "trace_duration_s",
    "llm_seconds",
    "tool_seconds",
    "first_tool_call_offset_s",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "reasoning_tokens",
    "total_tokens",
    "cache_adjusted_tokens",
    "cost_usd",
    "user_prompt_chars",
    "user_prompt",
]

TOOL_CALL_FIELDS = [
    "run",
    "app",
    "dataset",
    "golden_kind",
    "golden",
    "agent",
    "session_id",
    "turn_index",
    "call_index",
    "tool",
    "duration_s",
    "offset_s",
    "error",
    "is_duplicate",
    "is_discovery",
    "args_chars",
    "output_chars",
    "args",
]


class RunTables:
    """The three tables of one run, as lists of dicts."""

    def __init__(
        self, conversations: list[dict[str, Any]], turns: list[dict[str, Any]], tool_calls: list[dict[str, Any]]
    ):
        self.conversations = conversations
        self.turns = turns
        self.tool_calls = tool_calls

    def extend(self, other: RunTables) -> None:
        self.conversations.extend(other.conversations)
        self.turns.extend(other.turns)
        self.tool_calls.extend(other.tool_calls)


# --- helpers ------------------------------------------------------------------


def _metric_map(record: ConversationRecord) -> dict[str, dict[str, Any]]:
    return {m["name"]: m for m in record.metrics if "name" in m}


def _flag(value: bool | None) -> str | bool:
    return "" if value is None else value


def _round(value: float | None, digits: int = 3) -> float | str:
    return "" if value is None else round(value, digits)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _usage_sum(usages: Sequence[TurnUsage | None]) -> dict[str, Any]:
    acc = {k: 0 for k in ("input_tokens", "output_tokens", "cache_read_tokens", "reasoning_tokens", "requests")}
    cost = 0.0
    adjusted: list[int] = []
    for u in usages:
        if u is None:
            continue
        for k in acc:
            acc[k] += getattr(u, k) or 0
        cost += u.cost_usd or 0.0
        if u.cache_adjusted_tokens is not None:
            adjusted.append(u.cache_adjusted_tokens)
    acc["total_tokens"] = acc["input_tokens"] + acc["output_tokens"]
    acc["cache_adjusted_tokens"] = sum(adjusted)
    acc["mean_cache_adjusted_tokens_per_turn"] = round(sum(adjusted) / len(adjusted), 1) if adjusted else ""
    acc["cost_usd"] = round(cost, 6)
    # a turn whose run raised (usage limit, timeout) has token counts from the spans but no price
    acc["cost_complete"] = all(u is not None and u.cost_usd is not None for u in usages)
    return acc


def _trace_for(run_dir: Path, turn: TurnRecord) -> TurnTrace | None:
    if not turn.trace_path:
        return None
    path = run_dir / turn.trace_path
    if not path.exists():
        return None
    try:
        return load_trace(path)
    except Exception:  # noqa: BLE001 — a corrupt trace loses its breakdown columns, not the row
        return None


def _deterministic_breakdowns(
    record: ConversationRecord, run_dir: Path, app: BenchmarkApp
) -> dict[str, dict[str, Any]]:
    """Breakdowns of the deterministic metrics (deepeval's result record keeps only score and reason)."""
    out: dict[str, dict[str, Any]] = {}
    try:
        test_case = rebuild_test_case(run_dir, record)
    except Exception:  # noqa: BLE001
        return out
    meta = GoldenMeta.model_validate(record.metadata or {})
    metrics: list[Any] = [ToolEfficiencyMetric(app), TimeEfficiencyMetric(), TokenEfficiencyMetric()]
    if meta.is_gold:
        metrics.insert(0, SuccessMetric(app))
    for metric in metrics:
        try:
            metric.measure(test_case)
        except Exception as exc:  # noqa: BLE001 — the row loses this breakdown, the export goes on
            log.debug("%s: %s could not be recomputed: %s", record.name, metric.__name__, exc)
            continue
        out[metric.__name__] = {"score": metric.score, "success": metric.success, **(metric.score_breakdown or {})}
    if meta.checkpoints:
        try:
            fraction, reached = CompletionMetric(app, model=None)._checkpoints(test_case)
            out["Checkpoints"] = {"fraction": fraction, "reached": reached}
        except Exception as exc:  # noqa: BLE001
            log.debug("%s: checkpoints could not be recomputed: %s", record.name, exc)
    return out


# --- rows ---------------------------------------------------------------------


def conversation_row(
    record: ConversationRecord,
    turns: Sequence[TurnRecord],
    *,
    run_dir: Path,
    app: BenchmarkApp,
    app_name: str,
) -> dict[str, Any]:
    meta = GoldenMeta.model_validate(record.metadata or {})
    recorded = _metric_map(record)
    breakdowns = _deterministic_breakdowns(record, run_dir, app)
    turns = sorted(turns, key=lambda t: t.turn_index)
    traces = [_trace_for(run_dir, t) for t in turns]

    row: dict[str, Any] = {
        "run": record.run_name,
        "app": app_name,
        "dataset": record.dataset,
        "golden_kind": "gold" if meta.is_gold else "synthetic",
        "golden": record.golden_name,
        "agent": record.agent,
        "session_id": record.session_id or "",
        "conversation": record.name,
        "fully_specified": meta.fully_specified,
        "max_user_simulations": meta.max_user_simulations,
        "state_threshold": meta.state_threshold,
        "checkpoints": len(meta.checkpoints),
        "budget_seconds_per_turn": meta.budgets.seconds_per_turn if meta.budgets else "",
        "budget_tokens_per_turn": meta.budgets.tokens_per_turn if meta.budgets else "",
    }

    # metric scores: deepeval's record first, the direct deterministic measure as fallback
    for name, prefix in METRIC_COLUMNS.items():
        entry = recorded.get(name) or breakdowns.get(name) or {}
        row[f"{prefix}_score"] = _round(entry.get("score"), 4)
        row[f"{prefix}_pass"] = _flag(entry.get("success"))
    basis = "success" if meta.is_gold else "completion"
    row["correctness_basis"] = basis
    row["correct"] = row[f"{basis}_pass"]

    success_bd = breakdowns.get("Success", {})
    matched = success_bd.get("matched") or []
    missed = success_bd.get("missed") or []
    row["expected_fields"] = len(matched) + len(missed) if meta.is_gold else ""
    row["matched_fields"] = ";".join(matched)
    row["missed_fields"] = ";".join(missed)
    reached = breakdowns.get("Checkpoints", {}).get("reached")
    row["checkpoints_reached"] = ";".join(str(i) for i in reached) if reached else ""

    row["user_turns"] = sum(1 for t in record.turns if t.get("role") == "user")
    row["assistant_turns"] = len(turns)
    row["error_turns"] = sum(1 for t in turns if t.output_kind == "error")
    row["first_url_turn"] = next((t.turn_index for t in turns if t.final_url), "")
    row["final_url"] = next((t.final_url for t in reversed(turns) if t.final_url), "") or ""
    row["simulator_error"] = (record.metadata or {}).get("simulator_error", "") or ""

    tool_bd = breakdowns.get("Tool efficiency", {})
    wasted = tool_bd.get("wasted") or {}
    names = Counter(name for t in turns for name in t.tool_calls)
    row["tool_calls"] = sum(t.tool_call_count for t in turns)
    row["distinct_tools"] = len(names)
    row["wasted_tool_calls"] = sum(wasted.values()) if wasted else ""
    row["duplicate_tool_calls"] = wasted.get("duplicate", "")
    row["errored_tool_calls"] = wasted.get("errored", "")
    row["discovery_tool_calls"] = wasted.get("discovery", "")
    row["tool_calls_by_name"] = json.dumps(dict(sorted(names.items())), sort_keys=True) if names else ""

    seconds = [t.wall_clock_s for t in turns]
    row["seconds"] = round(sum(seconds), 3)
    row["mean_seconds_per_turn"] = round(sum(seconds) / len(seconds), 3) if seconds else ""
    row["max_seconds_per_turn"] = round(max(seconds), 3) if seconds else ""
    row["llm_seconds"] = round(sum(c.duration_s for tr in traces if tr for c in tr.llm_calls), 3)
    row["tool_seconds"] = round(sum(c.duration_s for tr in traces if tr for c in tr.tool_calls), 3)
    # a turn row is stamped when the turn ends: the conversation ran from the first
    # turn's start (its end minus its wall clock) to the last turn's end, simulator time included
    stamped = [(ts, t) for t in turns if (ts := _parse_ts(t.timestamp)) is not None]
    if stamped:
        first_end, first = min(stamped, key=lambda p: p[0])
        last_end = max(ts for ts, _ in stamped)
        started = first_end - timedelta(seconds=first.wall_clock_s)
        row["elapsed_seconds"] = round((last_end - started).total_seconds(), 3)
        row["started_at"] = started.isoformat()
        row["ended_at"] = last_end.isoformat()
    else:
        row["elapsed_seconds"] = row["started_at"] = row["ended_at"] = ""

    usage = _usage_sum([t.usage for t in turns])
    row["llm_requests"] = usage.pop("requests")
    row.update(usage)

    for name, column in (
        ("Success", "success_reason"),
        ("Completion", "completion_reason"),
        ("Tool efficiency", "tool_efficiency_reason"),
        ("Turn Relevancy", "turn_relevancy_reason"),
    ):
        row[column] = (recorded.get(name) or {}).get("reason") or ""
    return {field: row.get(field, "") for field in CONVERSATION_FIELDS}


def turn_row(turn: TurnRecord, trace: TurnTrace | None, *, app_name: str, golden_kind: str) -> dict[str, Any]:
    usage = turn.usage
    names = turn.tool_calls
    row = {
        "run": turn.run_name or turn.run_id or "",
        "app": app_name,
        "dataset": turn.dataset or "",
        "golden_kind": golden_kind,
        "golden": turn.golden_name or "",
        "agent": turn.agent,
        "session_id": turn.session_id,
        "turn_index": turn.turn_index,
        "timestamp": turn.timestamp,
        "output_kind": turn.output_kind,
        "has_url": bool(turn.final_url),
        "final_url": turn.final_url or "",
        "error_type": turn.error_type or "",
        "error_message": (turn.error_message or "")[:500],
        "tool_calls": turn.tool_call_count,
        "distinct_tools": len(set(names)),
        "tool_names": ";".join(names),
        "llm_requests": (
            usage.requests if usage and usage.requests is not None else len(trace.llm_calls) if trace else ""
        ),
        "wall_clock_s": round(turn.wall_clock_s, 3),
        "trace_duration_s": _round(trace.duration_s if trace else None),
        "llm_seconds": _round(sum(c.duration_s for c in trace.llm_calls) if trace else None),
        "tool_seconds": _round(sum(c.duration_s for c in trace.tool_calls) if trace else None),
        "first_tool_call_offset_s": _round(
            min((c.offset_s for c in trace.tool_calls), default=None) if trace else None
        ),
        "input_tokens": usage.input_tokens if usage else "",
        "output_tokens": usage.output_tokens if usage else "",
        "cache_read_tokens": usage.cache_read_tokens if usage else "",
        "reasoning_tokens": usage.reasoning_tokens if usage else "",
        "total_tokens": usage.total_tokens if usage else "",
        "cache_adjusted_tokens": usage.cache_adjusted_tokens if usage else "",
        "cost_usd": usage.cost_usd if usage else "",
        "user_prompt_chars": len(turn.user_prompt),
        "user_prompt": turn.user_prompt,
    }
    return {field: ("" if row.get(field) is None else row.get(field)) for field in TURN_FIELDS}


def tool_call_rows(
    turn: TurnRecord,
    trace: TurnTrace,
    *,
    app_name: str,
    golden_kind: str,
    fully_specified: bool,
    discovery_tools: frozenset[str],
    seen: set[str],
) -> list[dict[str, Any]]:
    """One row per tool call of a turn; ``seen`` carries the conversation's earlier (tool, args) keys."""
    rows: list[dict[str, Any]] = []
    for i, call in enumerate(trace.tool_calls, start=1):
        key = call.name + ":" + json.dumps(call.args or {}, sort_keys=True, default=str)
        args_text = json.dumps(call.args, sort_keys=True, default=str) if call.args is not None else ""
        rows.append(
            {
                "run": turn.run_name or turn.run_id or "",
                "app": app_name,
                "dataset": turn.dataset or "",
                "golden_kind": golden_kind,
                "golden": turn.golden_name or "",
                "agent": turn.agent,
                "session_id": turn.session_id,
                "turn_index": turn.turn_index,
                "call_index": i,
                "tool": call.name,
                "duration_s": round(call.duration_s, 4),
                "offset_s": round(call.offset_s, 3),
                "error": call.error or "",
                "is_duplicate": key in seen,
                "is_discovery": fully_specified and call.name in discovery_tools,
                "args_chars": len(args_text),
                "output_chars": len(call.output) if call.output else 0,
                "args": args_text[:2000],
            }
        )
        seen.add(key)
    return rows


# --- a whole run ---------------------------------------------------------------


def run_tables(run_dir: Path, *, app: BenchmarkApp | None = None) -> RunTables:
    run_dir = Path(run_dir)
    info = read_run_info(run_dir)
    app = app or app_for_run(run_dir, info.app)
    app_name = getattr(app, "name", info.app)
    conversations = load_conversations(run_dir)
    turns = load_turns(run_dir)

    by_session: dict[str, list[TurnRecord]] = {}
    for t in turns:
        by_session.setdefault(t.session_id, []).append(t)

    conv_rows: list[dict[str, Any]] = []
    turn_rows: list[dict[str, Any]] = []
    call_rows: list[dict[str, Any]] = []
    for record in conversations:
        session_turns = sorted(by_session.get(record.session_id or "", []), key=lambda t: t.turn_index)
        meta = GoldenMeta.model_validate(record.metadata or {})
        kind = "gold" if meta.is_gold else "synthetic"
        conv_rows.append(conversation_row(record, session_turns, run_dir=run_dir, app=app, app_name=app_name))
        seen: set[str] = set()
        for turn in session_turns:
            trace = _trace_for(run_dir, turn)
            turn_rows.append(turn_row(turn, trace, app_name=app_name, golden_kind=kind))
            if trace is not None:
                call_rows.extend(
                    tool_call_rows(
                        turn,
                        trace,
                        app_name=app_name,
                        golden_kind=kind,
                        fully_specified=meta.fully_specified,
                        discovery_tools=frozenset(getattr(app, "discovery_tools", ())),
                        seen=seen,
                    )
                )
    conv_rows.sort(key=lambda r: (r["dataset"], r["golden"], r["agent"]))
    return RunTables(conv_rows, turn_rows, call_rows)


def write_csv(rows: Sequence[dict[str, Any]], fields: Sequence[str], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def write_tables(tables: RunTables, out_dir: Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    return {
        "conversations": write_csv(tables.conversations, CONVERSATION_FIELDS, out_dir / CONVERSATIONS_CSV),
        "turns": write_csv(tables.turns, TURN_FIELDS, out_dir / TURNS_CSV),
        "tool_calls": write_csv(tables.tool_calls, TOOL_CALL_FIELDS, out_dir / TOOL_CALLS_CSV),
    }


def export_run(run_dir: Path, *, out_dir: Path | None = None, app: BenchmarkApp | None = None) -> dict[str, Path]:
    """Write the three CSV tables of one run to ``<run dir>/csv/`` (or ``out_dir``)."""
    run_dir = Path(run_dir)
    return write_tables(run_tables(run_dir, app=app), out_dir or run_dir / CSV_DIR)


def export_runs(run_dirs: Sequence[Path], out_dir: Path) -> dict[str, Path]:
    """Concatenate several runs into one set of tables (every row names its run)."""
    combined = RunTables([], [], [])
    for run_dir in run_dirs:
        combined.extend(run_tables(Path(run_dir)))
    return write_tables(combined, out_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dirs", nargs="+", type=Path, help="one or more results/<run-id> directories")
    parser.add_argument("--out", type=Path, help="write one combined set of tables here instead of <run>/csv/")
    args = parser.parse_args(argv)
    if args.out:
        paths = export_runs(args.run_dirs, args.out)
        print("wrote " + ", ".join(str(p) for p in paths.values()))
    else:
        for run_dir in args.run_dirs:
            paths = export_run(run_dir)
            print(f"{run_dir}: wrote " + ", ".join(p.name for p in paths.values()) + f" under {run_dir / CSV_DIR}")
    return 0


__all__ = [
    "CONVERSATIONS_CSV",
    "CONVERSATION_FIELDS",
    "CSV_DIR",
    "TOOL_CALLS_CSV",
    "TOOL_CALL_FIELDS",
    "TURNS_CSV",
    "TURN_FIELDS",
    "RunTables",
    "conversation_row",
    "export_run",
    "export_runs",
    "main",
    "run_tables",
    "tool_call_rows",
    "turn_row",
    "write_csv",
    "write_tables",
]


if __name__ == "__main__":
    raise SystemExit(main())
