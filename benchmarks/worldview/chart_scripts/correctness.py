# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9"]
# ///
"""Correctness, GeoUI vs VLM: share of tasks answered correctly, and the pass rate of each metric.

Left: ``correct`` rate per query set (gold: Success passed, the final map
matches the expected layers/date/view; synthetic: Completion passed, the
LLM judge says the user's goal was met). Right: pass rate of each of the six
metrics over all selected tasks. Bars are labelled ``k/n`` so a percentage
never hides a small sample.

    uv run benchmarks/worldview/chart_scripts/correctness.py

Writes correctness-<set>.png/.svg/.csv under <run>/charts/ (``--correct-only`` makes no sense here and is ignored).
"""

from __future__ import annotations

from common import (
    AGENTS,
    INK,
    INK_MUTED,
    grouped_bars,
    output_stem,
    parser,
    read_rows,
    report,
    save,
    select,
    setup_matplotlib,
    write_numbers,
)

SETS = [("gold", "Gold\n(Success)"), ("synthetic", "Synthetic\n(Completion)"), ("all", "All")]
METRICS = [
    ("success_pass", "Success"),
    ("completion_pass", "Completion"),
    ("tool_efficiency_pass", "Tool\nefficiency"),
    ("time_efficiency_pass", "Time\nefficiency"),
    ("token_efficiency_pass", "Token\nefficiency"),
    ("turn_relevancy_pass", "Turn\nrelevancy"),
]


def rate(rows: list[dict], column: str) -> tuple[float | None, int, int]:
    judged = [r[column] for r in rows if r.get(column) is not None]
    if not judged:
        return None, 0, 0
    k = sum(1 for v in judged if v)
    return 100 * k / len(judged), k, len(judged)


def main() -> None:
    args = parser(__doc__.splitlines()[0]).parse_args()
    args.correct_only = False
    args.set_name = "all"
    rows = read_rows(args.run)
    selections = {s: select(rows, set_name=s, paired=args.paired) for s, _ in SETS}

    plt = setup_matplotlib()
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(16, 6.4), gridspec_kw={"width_ratios": [1, 1.7]})
    fig.subplots_adjust(bottom=0.2, top=0.84, wspace=0.18)

    numbers = []
    left = {a: [] for a in AGENTS}
    counts = {a: [] for a in AGENTS}
    for s, _ in SETS:
        groups = selections[s].by_agent()
        for a in AGENTS:
            pct, k, n = rate(groups[a], "correct")
            left[a].append(pct)
            counts[a].append(f"{k}/{n}")
            numbers.append(("correct", s, a, pct, k, n))
    _plot(ax, [t for _, t in SETS], left, counts)
    ax.set_ylabel("Tasks correct (%)", fontweight="bold")
    ax.set_title("Correct answers", fontsize=13, fontweight="bold", color=INK, loc="left")
    ax.legend(loc="upper right", bbox_to_anchor=(1, 1.02), frameon=False, handlelength=2.5, handleheight=1.4)

    groups = selections["all"].by_agent()
    right = {a: [] for a in AGENTS}
    rcounts = {a: [] for a in AGENTS}
    for col, _ in METRICS:
        for a in AGENTS:
            pct, k, n = rate(groups[a], col)
            right[a].append(pct)
            rcounts[a].append(f"{k}/{n}")
            numbers.append((col, "all", a, pct, k, n))
    _plot(ax2, [t for _, t in METRICS], right, rcounts)
    ax2.set_title("Pass rate per metric (all queries)", fontsize=13, fontweight="bold", color=INK, loc="left")

    fig.suptitle("GeoUI vs VLM — did the agent get it right?", fontsize=15, fontweight="bold", x=0.06, ha="left")
    fig.text(
        0.06, 0.03,
        selections["all"].footnote("Success is judged on gold queries only (synthetic ones have no expected state)."),
        fontsize=9, color=INK_MUTED, style="italic",
    )  # fmt: skip

    stem = output_stem(args, "correctness")
    written = save(fig, stem)
    written.append(write_numbers(stem, ["measure", "set", "agent", "percent", "passed", "judged"], numbers))
    report(selections["all"], written)


def _plot(ax, categories, values, counts):
    labels = {a: dict(zip(range(len(categories)), counts[a], strict=True)) for a in AGENTS}
    for agent in AGENTS:  # grouped_bars labels by value; pair each value with its k/n here
        values[agent] = [_Labelled(v, f"{v:.0f}%\n{labels[agent][i]}") if v is not None else None
                         for i, v in enumerate(values[agent])]  # fmt: skip
    grouped_bars(ax, categories, values, log=False, label=lambda v: v.text, label_zero=True)
    ax.set_ylim(0, 125)
    ax.set_yticks([0, 25, 50, 75, 100])


class _Labelled(float):
    """A bar height that carries its own label text."""

    def __new__(cls, value: float, text: str):
        obj = super().__new__(cls, value)
        obj.text = text
        return obj


if __name__ == "__main__":
    main()
