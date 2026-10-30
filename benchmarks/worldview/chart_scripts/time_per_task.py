# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9"]
# ///
"""Time per task, GeoUI vs VLM: mean agent seconds per conversation, by query set.

Agent seconds = the sum of the agent's own turn times (``seconds`` in
conversations.csv), which excludes the simulated user's thinking time. Each
group is one query set (gold, synthetic, both); the label on the VLM bar is
its ratio to GeoUI. The right panel splits the same seconds into time waiting
on the model and time running tools (the rest is framework overhead).

    uv run benchmarks/worldview/chart_scripts/time_per_task.py
    uv run benchmarks/worldview/chart_scripts/time_per_task.py --correct-only

Writes time_per_task-<set>.png/.svg/.csv under <run>/charts/ (``--set`` is ignored: every set is shown).
"""

from __future__ import annotations

from common import (
    AGENT_COLOR,
    AGENT_HATCH,
    AGENT_LABEL,
    AGENTS,
    GRID,
    INK,
    INK_MUTED,
    grouped_bars,
    mean_of,
    output_stem,
    parser,
    ratio,
    read_rows,
    report,
    save,
    select,
    setup_matplotlib,
    times,
    write_numbers,
)

SETS = [("gold", "Gold queries"), ("synthetic", "Synthetic queries"), ("all", "All queries")]


def minutes(v: float | None) -> str:
    if v is None:
        return "–"
    return f"{v:.0f} s" if v < 120 else f"{v / 60:.1f} min"


def main() -> None:
    args = parser(__doc__.splitlines()[0]).parse_args()
    args.set_name = "all"
    rows = read_rows(args.run)
    selections = {s: select(rows, set_name=s, paired=args.paired, correct_only=args.correct_only) for s, _ in SETS}
    means = {a: [mean_of(selections[s].by_agent()[a], "seconds") for s, _ in SETS] for a in AGENTS}

    plt = setup_matplotlib()
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15, 6.4), gridspec_kw={"width_ratios": [1.5, 1]})
    fig.subplots_adjust(bottom=0.2, top=0.84, wspace=0.25)

    labels = [f"{title}\n(n={selections[s].n('geoui')} tasks)" for s, title in SETS]
    grouped_bars(ax, labels, means, log=False, label=minutes)
    for i, _ in enumerate(SETS):
        r = ratio(means["vlm"][i], means["geoui"][i])
        if r is not None and means["vlm"][i] is not None:
            ax.annotate(
                f"{times(r)} slower",
                (i + 0.19, means["vlm"][i]),
                xytext=(0, 18),
                textcoords="offset points",
                ha="center",
                fontsize=10,
                color=INK_MUTED,
            )
    ax.set_ylabel("Mean agent seconds per task", fontweight="bold")
    ax.set_ylim(0, max(v for vals in means.values() for v in vals if v) * 1.25)
    ax.set_title("Agent time per task", fontsize=13, fontweight="bold", color=INK, loc="left")
    ax.legend(loc="upper left", frameon=False, handlelength=2.5, handleheight=1.4)

    # right: where the time goes, on the "all" selection
    sel = selections["all"]
    groups = sel.by_agent()
    split_rows = []
    axis_max = max(mean_of(groups[a], "seconds") or 0 for a in AGENTS) * 1.2
    for i, agent in enumerate(AGENTS):
        llm = mean_of(groups[agent], "llm_seconds") or 0
        tool = mean_of(groups[agent], "tool_seconds") or 0
        total = mean_of(groups[agent], "seconds") or 0
        other = max(0.0, total - llm - tool)
        split_rows.append((agent, llm, tool, other, total))
        left = 0.0
        for part, value, alpha in (("model", llm, 1.0), ("tools", tool, 0.55), ("other", other, 0.2)):
            ax2.barh(
                i, value, left=left, height=0.5, color=AGENT_COLOR[agent], alpha=alpha,
                hatch=AGENT_HATCH[agent] if part == "model" else None, edgecolor="white", linewidth=2,
            )  # fmt: skip
            if value / max(axis_max, 1) > 0.08:
                ax2.text(left + value / 2, i, f"{part}\n{minutes(value)}", ha="center", va="center", fontsize=9,
                         color="white" if part == "model" else INK)  # fmt: skip
            left += value
        detail = "" if total / max(axis_max, 1) > 0.25 else f"  (model {minutes(llm)}, tools {minutes(tool)})"
        ax2.text(total, i, f"  {minutes(total)}{detail}", va="center", fontsize=10, fontweight="bold", color=INK)
    ax2.set_yticks(range(len(AGENTS)))
    ax2.set_yticklabels([AGENT_LABEL[a] for a in AGENTS])
    ax2.invert_yaxis()
    ax2.set_xlabel("Mean seconds per task (all queries)")
    ax2.grid(axis="x", color=GRID)
    ax2.set_axisbelow(True)
    ax2.set_xlim(0, axis_max)
    ax2.set_title("Where the time goes", fontsize=13, fontweight="bold", color=INK, loc="left")

    fig.suptitle("GeoUI vs VLM — time to complete a task", fontsize=15, fontweight="bold", x=0.06, ha="left")
    fig.text(
        0.06, 0.03,
        sel.footnote("Agent seconds exclude the simulated user's time. 'Other' = framework and MCP overhead."),
        fontsize=9, color=INK_MUTED, style="italic",
    )  # fmt: skip

    stem = output_stem(args, "time_per_task")
    written = save(fig, stem)
    written.append(
        write_numbers(
            stem,
            ["section", "set_or_agent", "geoui", "vlm", "vlm_over_geoui", "n_geoui", "n_vlm"],
            [
                (
                    "mean_seconds",
                    s,
                    means["geoui"][i],
                    means["vlm"][i],
                    ratio(means["vlm"][i], means["geoui"][i]),
                    selections[s].n("geoui"),
                    selections[s].n("vlm"),
                )
                for i, (s, _) in enumerate(SETS)
            ]
            + [
                ("split_llm_tool_other_total", a, llm, tool, other, total, "")
                for a, llm, tool, other, total in split_rows
            ],
        )
    )
    report(sel, written)


if __name__ == "__main__":
    main()
