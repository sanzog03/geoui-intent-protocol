"""Pure aggregation of a run: per golden × agent rows, cross-agent ratios, per-agent totals.

Input is what a run directory holds (``conversations.jsonl`` with the metric
scores, ``turns.jsonl``); output is a :class:`Summary` that ``summarize.py``
writes as ``summary.json`` and renders as ``summary.md``. The comparison is
expressed as ratios of every other agent kind over a reference kind.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from statistics import mean
from typing import Any

from pydantic import BaseModel, Field

from geobench.harness import ConversationRecord
from geobench.records import TurnRecord, TurnUsage

METRIC_ORDER = ["Success", "Completion", "Tool efficiency", "Time efficiency", "Token efficiency", "Turn Relevancy"]
RATIO_FIELDS = ("tool_calls", "seconds", "cache_adjusted_tokens", "total_tokens")


class MetricScore(BaseModel):
    score: float | None = None
    success: bool | None = None
    threshold: float | None = None
    reason: str | None = None


class ConversationRow(BaseModel):
    golden: str
    agent: str
    dataset: str
    session_id: str | None = None
    turns: int = 0
    error_turns: int = 0
    tool_calls: int = 0
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    cache_adjusted_tokens: int = 0
    requests: int = 0
    cost_usd: float = 0.0
    final_url: str | None = None
    metrics: dict[str, MetricScore] = Field(default_factory=dict)


class AgentTotals(BaseModel):
    agent: str
    conversations: int
    turns: int
    error_turns: int
    tool_calls: int
    seconds: float
    total_tokens: int
    cache_adjusted_tokens: int
    cost_usd: float
    pass_rate: dict[str, float | None] = Field(default_factory=dict, description="metric → fraction passed")
    mean_score: dict[str, float | None] = Field(default_factory=dict, description="metric → mean score")


class Summary(BaseModel):
    run_name: str | None = None
    reference_agent: str
    rows: list[ConversationRow]
    ratios: dict[str, dict[str, dict[str, float | None]]] = Field(
        default_factory=dict, description="golden → 'other/reference' → field → ratio"
    )
    totals: list[AgentTotals]
    metric_names: list[str]


def _usage_sum(usages: Iterable[TurnUsage | None]) -> dict[str, Any]:
    acc = {k: 0 for k in ("input_tokens", "output_tokens", "cache_read_tokens", "reasoning_tokens", "requests")}
    cost = 0.0
    adjusted = 0
    for u in usages:
        if u is None:
            continue
        for k in acc:
            acc[k] += getattr(u, k) or 0
        cost += u.cost_usd or 0.0
        adjusted += u.cache_adjusted_tokens or 0
    acc["total_tokens"] = acc["input_tokens"] + acc["output_tokens"]
    acc["cache_adjusted_tokens"] = adjusted
    acc["cost_usd"] = round(cost, 6)
    return acc


def rows_from_records(
    conversations: Sequence[ConversationRecord], turns: Sequence[TurnRecord]
) -> list[ConversationRow]:
    by_session: dict[str, list[TurnRecord]] = defaultdict(list)
    for t in turns:
        by_session[t.session_id].append(t)
    rows: list[ConversationRow] = []
    for conv in conversations:
        session_turns = sorted(by_session.get(conv.session_id or "", []), key=lambda t: t.turn_index)
        usage = _usage_sum(t.usage for t in session_turns)
        final_url = next((t.final_url for t in reversed(session_turns) if t.final_url), None)
        metrics = {
            m["name"]: MetricScore(
                score=m.get("score"), success=m.get("success"), threshold=m.get("threshold"), reason=m.get("reason")
            )
            for m in conv.metrics
            if "name" in m
        }
        rows.append(
            ConversationRow(
                golden=conv.golden_name,
                agent=conv.agent,
                dataset=conv.dataset,
                session_id=conv.session_id,
                turns=len(session_turns),
                error_turns=sum(1 for t in session_turns if t.output_kind == "error"),
                tool_calls=sum(t.tool_call_count for t in session_turns),
                seconds=round(sum(t.wall_clock_s for t in session_turns), 3),
                final_url=final_url,
                metrics=metrics,
                **usage,
            )
        )
    return rows


def _ratio(num: float, den: float) -> float | None:
    if den == 0:
        return None
    return round(num / den, 3)


def ratios_for(rows: Sequence[ConversationRow], reference: str) -> dict[str, dict[str, dict[str, float | None]]]:
    by_golden: dict[str, dict[str, ConversationRow]] = defaultdict(dict)
    for row in rows:
        by_golden[row.golden][row.agent] = row  # one row per golden × agent (last wins on reruns)
    out: dict[str, dict[str, dict[str, float | None]]] = {}
    for golden, by_agent in by_golden.items():
        ref = by_agent.get(reference)
        if ref is None:
            continue
        for agent, row in by_agent.items():
            if agent == reference:
                continue
            out.setdefault(golden, {})[f"{agent}/{reference}"] = {
                field: _ratio(getattr(row, field), getattr(ref, field)) for field in RATIO_FIELDS
            }
    return out


def totals_for(rows: Sequence[ConversationRow], metric_names: Sequence[str]) -> list[AgentTotals]:
    by_agent: dict[str, list[ConversationRow]] = defaultdict(list)
    for row in rows:
        by_agent[row.agent].append(row)
    totals: list[AgentTotals] = []
    for agent, agent_rows in sorted(by_agent.items()):
        pass_rate: dict[str, float | None] = {}
        mean_score: dict[str, float | None] = {}
        for name in metric_names:
            scored = [r.metrics[name] for r in agent_rows if name in r.metrics and r.metrics[name].score is not None]
            judged = [m for m in scored if m.success is not None]
            mean_score[name] = round(mean(m.score for m in scored), 4) if scored else None
            pass_rate[name] = round(sum(1 for m in judged if m.success) / len(judged), 4) if judged else None
        totals.append(
            AgentTotals(
                agent=agent,
                conversations=len(agent_rows),
                turns=sum(r.turns for r in agent_rows),
                error_turns=sum(r.error_turns for r in agent_rows),
                tool_calls=sum(r.tool_calls for r in agent_rows),
                seconds=round(sum(r.seconds for r in agent_rows), 3),
                total_tokens=sum(r.total_tokens for r in agent_rows),
                cache_adjusted_tokens=sum(r.cache_adjusted_tokens for r in agent_rows),
                cost_usd=round(sum(r.cost_usd for r in agent_rows), 6),
                pass_rate=pass_rate,
                mean_score=mean_score,
            )
        )
    return totals


def summarize(
    conversations: Sequence[ConversationRecord],
    turns: Sequence[TurnRecord],
    *,
    reference_agent: str,
    run_name: str | None = None,
) -> Summary:
    rows = rows_from_records(conversations, turns)
    seen = {name for row in rows for name in row.metrics}
    metric_names = [m for m in METRIC_ORDER if m in seen] + sorted(seen - set(METRIC_ORDER))
    return Summary(
        run_name=run_name,
        reference_agent=reference_agent,
        rows=sorted(rows, key=lambda r: (r.dataset, r.golden, r.agent)),
        ratios=ratios_for(rows, reference_agent),
        totals=totals_for(rows, metric_names),
        metric_names=metric_names,
    )


# --- markdown -----------------------------------------------------------------


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "–"
    return f"{value:.{digits}f}"


def _k(value: int) -> str:
    return f"{value / 1000:.1f}k" if value >= 1000 else str(value)


def render_markdown(summary: Summary) -> str:
    names = summary.metric_names
    short = {n: n.replace(" efficiency", " eff").replace("Turn Relevancy", "Relevancy") for n in names}
    lines = [f"# Benchmark summary — {summary.run_name or 'run'}", ""]
    lines.append(
        f"Reference agent for ratios: `{summary.reference_agent}`. "
        "Scores are deepeval metric scores (pass ✓ / fail ✗ at the metric's threshold); "
        "tokens are cache-adjusted per prompts.md (input − cache_read + 0.1·cache_read + output)."
    )
    lines.append("")
    header = ["scenario", "agent", *[short[n] for n in names], "turns", "tool calls", "s", "tokens", "cost $"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")
    by_golden: dict[str, list[ConversationRow]] = defaultdict(list)
    for row in summary.rows:
        by_golden[row.golden].append(row)
    for golden, rows in by_golden.items():
        for row in rows:
            cells = [golden, row.agent]
            for n in names:
                m = row.metrics.get(n)
                if m is None or m.score is None:
                    cells.append("–")
                else:
                    mark = "" if m.success is None else (" ✓" if m.success else " ✗")
                    cells.append(f"{m.score:.2f}{mark}")
            cells += [
                str(row.turns),
                str(row.tool_calls),
                _fmt(row.seconds, 0),
                _k(row.cache_adjusted_tokens),
                _fmt(row.cost_usd, 3),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        for pair, fields in summary.ratios.get(golden, {}).items():
            cells = [
                "",
                f"**{pair}**",
                *["" for _ in names],
                "",
                f"{_fmt(fields['tool_calls'], 1)}×",
                f"{_fmt(fields['seconds'], 1)}×",
                f"{_fmt(fields['cache_adjusted_tokens'], 1)}×",
                "",
            ]
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Per-agent totals")
    lines.append("")
    theader = [
        "agent",
        "conversations",
        "turns",
        "error turns",
        "tool calls",
        "s",
        "tokens",
        "cost $",
        *[f"{short[n]} pass" for n in names],
        *[f"{short[n]} mean" for n in names],
    ]
    lines.append("| " + " | ".join(theader) + " |")
    lines.append("|" + "|".join("---" for _ in theader) + "|")
    for t in summary.totals:
        cells = [
            t.agent,
            str(t.conversations),
            str(t.turns),
            str(t.error_turns),
            str(t.tool_calls),
            _fmt(t.seconds, 0),
            _k(t.cache_adjusted_tokens),
            _fmt(t.cost_usd, 3),
        ]
        cells += [_fmt(t.pass_rate.get(n)) for n in names]
        cells += [_fmt(t.mean_score.get(n)) for n in names]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "METRIC_ORDER",
    "RATIO_FIELDS",
    "AgentTotals",
    "ConversationRow",
    "MetricScore",
    "Summary",
    "ratios_for",
    "render_markdown",
    "rows_from_records",
    "summarize",
    "totals_for",
]
