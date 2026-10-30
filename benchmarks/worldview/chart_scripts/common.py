"""Shared loading, filtering and styling for the chart scripts.

Everything the charts plot comes from ``<run>/csv/conversations.csv`` (one row
per query x agent), written by ``python -m geouibench export``. This module
only reads that file; it never recomputes a metric.

Filtering rules, applied in this order and printed by every script:

1. ``--set`` keeps gold queries, synthetic queries, or both.
2. Rows with a ``simulator_error`` are dropped: the simulated user failed and
   the agent never ran, so the row has no turns and would read as "free".
3. ``--paired`` (default on) keeps only queries where every agent still has a
   row, so both bars average over the same tasks.
4. ``--correct-only`` keeps, per agent, only conversations the agent got
   right (``correct`` = Success on gold, Completion on synthetic). With
   ``--paired`` this keeps only queries that *both* agents got right.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_RUN = REPO / "benchmarks" / "worldview" / "results" / "2026-10-30-all"

AGENTS = ("geoui", "vlm")  # fixed order: GeoUI first, always the same colour
AGENT_LABEL = {"geoui": "GeoUI", "vlm": "VLM"}
AGENT_DESCRIPTION = {"geoui": "intent protocol", "vlm": "browser computer-use"}
# Validated with the dataviz skill's validate_palette.js (light surface): CVD dE 24, normal dE 29.6.
# The orange is below 3:1 contrast on white, so every bar carries a printed value and a hatch.
AGENT_COLOR = {"geoui": "#3F7FB0", "vlm": "#E39B2F"}
AGENT_HATCH = {"geoui": "xxx", "vlm": ".."}
CALLOUT_DARK = "#1F3A8A"
INK = "#1A1A1A"
INK_MUTED = "#5F6368"
GRID = "#E3E3E3"

INT_COLUMNS = {
    "assistant_turns", "user_turns", "error_turns", "tool_calls", "distinct_tools", "wasted_tool_calls",
    "duplicate_tool_calls", "errored_tool_calls", "discovery_tool_calls", "llm_requests", "input_tokens",
    "output_tokens", "cache_read_tokens", "reasoning_tokens", "total_tokens", "cache_adjusted_tokens",
}  # fmt: skip
FLOAT_COLUMNS = {
    "seconds", "mean_seconds_per_turn", "max_seconds_per_turn", "llm_seconds", "tool_seconds", "elapsed_seconds",
    "cost_usd", "success_score", "completion_score", "tool_efficiency_score", "time_efficiency_score",
    "token_efficiency_score", "turn_relevancy_score", "mean_cache_adjusted_tokens_per_turn",
}  # fmt: skip
BOOL_COLUMNS = {
    "correct", "cost_complete", "success_pass", "completion_pass", "tool_efficiency_pass", "time_efficiency_pass",
    "token_efficiency_pass", "turn_relevancy_pass",
}  # fmt: skip


def _coerce(name: str, value: str):
    if value == "":
        return None
    if name in INT_COLUMNS:
        return int(float(value))
    if name in FLOAT_COLUMNS:
        return float(value)
    if name in BOOL_COLUMNS:
        return value == "True"
    return value


def read_rows(run_dir: Path) -> list[dict]:
    path = Path(run_dir) / "csv" / "conversations.csv"
    if not path.exists():
        raise SystemExit(f"{path} not found; run `uv run python -m geouibench export {run_dir}` first")
    with path.open(encoding="utf-8", newline="") as f:
        return [{k: _coerce(k, v) for k, v in row.items()} for row in csv.DictReader(f)]


@dataclass
class Selection:
    """The rows a chart plots, plus a record of what was filtered out and why."""

    rows: list[dict]
    run: str
    set_name: str
    paired: bool
    correct_only: bool
    notes: list[str] = field(default_factory=list)
    short_notes: list[str] = field(default_factory=list)

    def by_agent(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {a: [] for a in AGENTS}
        for r in self.rows:
            out.setdefault(r["agent"], []).append(r)
        return out

    def n(self, agent: str) -> int:
        return sum(1 for r in self.rows if r["agent"] == agent)

    def queries(self) -> list[str]:
        return sorted({r["golden"] for r in self.rows})

    def footnote(self, lead: str = "") -> str:
        """One line for under a chart: the run, what a bar averages over, and what was left out."""
        parts = [f"Run {self.run}.", lead] if lead else [f"Run {self.run}."]
        parts += [n[0].upper() + n[1:] + "." for n in self.short_notes]
        return " ".join(p for p in parts if p)

    def describe(self) -> str:
        set_text = {"gold": "gold queries", "synthetic": "synthetic queries", "all": "gold + synthetic queries"}
        parts = [set_text[self.set_name]]
        parts.append("same tasks for both agents" if self.paired else "all completed tasks per agent")
        if self.correct_only:
            parts.append("correct answers only")
        return ", ".join(parts)


def select(
    rows: Sequence[dict], *, set_name: str = "all", paired: bool = True, correct_only: bool = False
) -> Selection:
    run = rows[0]["run"] if rows else "?"
    notes: list[str] = []
    kept = [r for r in rows if set_name == "all" or r["golden_kind"] == set_name]

    failed = [r for r in kept if r.get("simulator_error")]
    if failed:
        notes.append(
            f"dropped {len(failed)} conversation(s) the simulated user never started: "
            + ", ".join(f"{r['golden']}[{r['agent']}]" for r in failed)
        )
    kept = [r for r in kept if not r.get("simulator_error")]
    short: list[str] = []
    if failed:
        short.append(f"{len(failed)} conversation(s) never started (simulated-user API error) and are excluded")

    if correct_only:
        wrong = [r for r in kept if not r.get("correct")]
        if wrong:
            notes.append(f"dropped {len(wrong)} incorrect conversation(s)")
        kept = [r for r in kept if r.get("correct")]
        short.append("correct answers only")

    if paired:
        agents_by_query: dict[str, set[str]] = defaultdict(set)
        for r in kept:
            agents_by_query[r["golden"]].add(r["agent"])
        complete = {q for q, a in agents_by_query.items() if a >= set(AGENTS)}
        unpaired = sorted(q for q in agents_by_query if q not in complete)
        if unpaired:
            notes.append(f"dropped {len(unpaired)} query(ies) without a row for every agent: {', '.join(unpaired)}")
        kept = [r for r in kept if r["golden"] in complete]
        if unpaired:
            short.append(f"{len(unpaired)} query(ies) lacking a row for both agents are excluded for both")

    return Selection(kept, run, set_name, paired, correct_only, notes, short)


def mean_of(rows: Iterable[dict], column: str) -> float | None:
    values = [r[column] for r in rows if r.get(column) is not None]
    return statistics.fmean(values) if values else None


def ratio(vlm: float | None, geoui: float | None) -> float | None:
    if vlm is None or geoui in (None, 0):
        return None
    return vlm / geoui


def human(value: float | None) -> str:
    """12 / 764 / 48k / 1.2M, as on the slide."""
    if value is None:
        return "–"
    v = abs(value)
    if v >= 1e6:
        return f"{value / 1e6:.1f}M"
    if v >= 1e4:
        return f"{value / 1e3:.0f}k"
    if v >= 1e3:
        return f"{value / 1e3:.1f}k"
    if v >= 10 or float(value).is_integer():
        return f"{value:.0f}"
    return f"{value:.1f}"


def times(value: float | None) -> str:
    if value is None or value == 0:
        return "–"
    return f"{value:.0f}×" if value >= 10 else f"{value:.1f}×"


def parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--run", type=Path, default=DEFAULT_RUN, help="results/<run-id> directory (default: %(default)s)")
    p.add_argument("--set", dest="set_name", choices=("all", "gold", "synthetic"), default="all")
    p.add_argument(
        "--unpaired", dest="paired", action="store_false", help="average every completed task per agent, unmatched"
    )
    p.add_argument("--correct-only", action="store_true", help="only conversations the agent got right")
    p.add_argument("--out", type=Path, help="output directory (default: <run>/charts)")
    return p


def output_stem(args: argparse.Namespace, name: str) -> Path:
    out_dir = args.out or Path(args.run) / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{args.set_name}" + ("" if args.paired else "-unpaired") + ("-correct" if args.correct_only else "")
    return out_dir / f"{name}-{suffix}"


def write_numbers(stem: Path, header: Sequence[str], rows: Iterable[Sequence]) -> Path:
    """The exact numbers a chart plots, beside the image, so every bar can be checked."""
    path = stem.with_suffix(".csv")
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for row in rows:
            w.writerow(["" if v is None else (round(v, 4) if isinstance(v, float) else v) for v in row])
    return path


def report(selection: Selection, written: Sequence[Path]) -> None:
    print(f"run {selection.run}: {selection.describe()}")
    print("  n per agent: " + ", ".join(f"{AGENT_LABEL[a]}={selection.n(a)}" for a in AGENTS))
    for note in selection.notes:
        print(f"  {note}")
    for path in written:
        print(f"  wrote {path}")


def setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.edgecolor": INK_MUTED,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK_MUTED,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "hatch.color": "white",
            "hatch.linewidth": 1.0,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
        }
    )
    return plt


def save(fig, stem: Path) -> list[Path]:
    paths = [stem.with_suffix(".png"), stem.with_suffix(".svg")]
    for p in paths:
        fig.savefig(p)
    return paths


def grouped_bars(
    ax,
    categories: Sequence[str],
    values: dict[str, Sequence[float | None]],
    *,
    log: bool,
    label: Callable[[float | None], str] = human,
    width: float = 0.36,
    label_zero: bool = False,
) -> None:
    """Side-by-side bars, GeoUI left, VLM right, value printed on each bar (text in ink, not series colour)."""
    xs = range(len(categories))
    for i, agent in enumerate(AGENTS):
        offset = (i - 0.5) * (width + 0.02)  # a small surface gap between the pair
        vals = values[agent]
        heights = [v if v is not None else 0 for v in vals]
        bars = ax.bar(
            [x + offset for x in xs],
            heights,
            width,
            color=AGENT_COLOR[agent],
            hatch=AGENT_HATCH[agent],
            edgecolor="white",
            linewidth=0,
            label=AGENT_LABEL[agent],
            zorder=2,
        )
        for bar, v in zip(bars, vals, strict=True):
            if v is None or (v <= 0 and not label_zero):
                continue
            y = bar.get_height()
            ax.annotate(
                label(v),
                (bar.get_x() + bar.get_width() / 2, y),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold",
                color=INK,
            )
    ax.set_xticks(list(xs))
    ax.set_xticklabels(categories)
    if log:
        ax.set_yscale("log")
    ax.grid(axis="y", which="major", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def callouts(fig, rect: Sequence[float], items: Sequence[tuple[str, str]]) -> None:
    """The stacked headline tiles on the right: first one filled, the rest outlined."""
    from matplotlib.patches import FancyBboxPatch

    left, bottom, w, h = rect
    gap = 0.03
    tile_h = (h - gap * (len(items) - 1)) / len(items)
    for i, (big, small) in enumerate(items):
        y = bottom + h - (i + 1) * tile_h - i * gap
        first = i == 0
        fig.patches.append(
            FancyBboxPatch(
                (left, y),
                w,
                tile_h,
                boxstyle="round,pad=0,rounding_size=0.012",
                transform=fig.transFigure,
                facecolor=CALLOUT_DARK if first else "#F3F3F3",
                edgecolor=CALLOUT_DARK if first else "#D0D0D0",
                linewidth=1,
                zorder=0,
            )
        )
        fig.text(
            left + 0.02,
            y + tile_h * 0.58,
            big,
            fontsize=30,
            fontweight="bold",
            color="white" if first else CALLOUT_DARK,
            va="center",
        )
        fig.text(
            left + 0.02,
            y + tile_h * 0.25,
            small,
            fontsize=13,
            color="#DCE3F5" if first else INK,
            va="center",
        )
