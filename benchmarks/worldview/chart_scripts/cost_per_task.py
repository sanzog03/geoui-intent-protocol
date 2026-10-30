# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9"]
# ///
"""Per-task cost, GeoUI vs VLM: mean tokens, requests and tool calls per conversation (log scale).

The slide chart: seven grouped bars (input, output, total, cache-read and
reasoning tokens, LLM requests, tool calls), each the mean over the selected
conversations, with three headline ratios on the right (VLM mean / GeoUI mean).

    uv run benchmarks/worldview/chart_scripts/cost_per_task.py                 # gold + synthetic, paired
    uv run benchmarks/worldview/chart_scripts/cost_per_task.py --set gold
    uv run benchmarks/worldview/chart_scripts/cost_per_task.py --correct-only

Writes cost_per_task-<set>.png/.svg and a .csv of the plotted means under <run>/charts/.
"""

from __future__ import annotations

from common import (
    AGENT_DESCRIPTION,
    AGENT_LABEL,
    AGENTS,
    INK,
    INK_MUTED,
    callouts,
    grouped_bars,
    human,
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

#: (column in conversations.csv, axis label), in the slide's order.
MEASURES = [
    ("input_tokens", "Input\ntokens"),
    ("output_tokens", "Output\ntokens"),
    ("total_tokens", "Total\ntokens"),
    ("llm_requests", "Requests"),
    ("tool_calls", "Tool\ncalls"),
    ("reasoning_tokens", "Reasoning\ntokens"),
    ("cache_read_tokens", "Cache-read\ntokens"),
]

#: The three headline tiles: (column, how the tile phrases it).
HEADLINES = [
    ("total_tokens", "fewer total tokens"),
    ("tool_calls", "fewer tool calls"),
    ("llm_requests", "fewer requests"),
]


def main() -> None:
    args = parser(__doc__.splitlines()[0]).parse_args()
    selection = select(read_rows(args.run), set_name=args.set_name, paired=args.paired, correct_only=args.correct_only)
    groups = selection.by_agent()
    means = {a: [mean_of(groups[a], col) for col, _ in MEASURES] for a in AGENTS}
    by_col = {col: {a: means[a][i] for a in AGENTS} for i, (col, _) in enumerate(MEASURES)}

    plt = setup_matplotlib()
    fig = plt.figure(figsize=(16, 7.2))
    ax = fig.add_axes([0.05, 0.2, 0.62, 0.63])
    grouped_bars(ax, [label for _, label in MEASURES], means, log=True)
    ax.set_ylabel("Mean per task (log scale)", fontweight="bold")
    ns = {a: selection.n(a) for a in AGENTS}
    n_text = (
        f"n={ns['geoui']} tasks"
        if ns["geoui"] == ns["vlm"]
        else ", ".join(f"{AGENT_LABEL[a]} n={ns[a]}" for a in AGENTS)
    )
    ax.set_title(f"GeoUI vs VLM — mean cost per task ({n_text})", fontsize=14, fontweight="bold", color=INK, pad=14)
    ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False, handlelength=2.5, handleheight=1.4
    )
    top = max(v for vals in means.values() for v in vals if v)
    ax.set_ylim(1, top * 4)

    fig.text(
        0.05,
        0.93,
        f"Per-task cost, {selection.describe()} (log scale)  ·  "
        + "   ".join(f"{AGENT_LABEL[a]} — {AGENT_DESCRIPTION[a]}" for a in AGENTS),
        fontsize=13,
        color=INK,
    )
    footnote = selection.footnote("Mean over conversations; a multi-turn conversation counts as one task.")
    fig.text(0.05, 0.015, footnote, fontsize=9, color=INK_MUTED, style="italic")

    tiles = []
    for col, phrase in HEADLINES:
        g, v = by_col[col]["geoui"], by_col[col]["vlm"]
        tiles.append((times(ratio(v, g)), f"{phrase} — {human(g)} vs {human(v)}"))
    callouts(fig, [0.71, 0.22, 0.27, 0.58], tiles)

    stem = output_stem(args, "cost_per_task")
    written = save(fig, stem)
    written.append(
        write_numbers(
            stem,
            ["measure", "geoui_mean", "vlm_mean", "vlm_over_geoui", "geoui_n", "vlm_n"],
            [
                (
                    col,
                    by_col[col]["geoui"],
                    by_col[col]["vlm"],
                    ratio(by_col[col]["vlm"], by_col[col]["geoui"]),
                    ns["geoui"],
                    ns["vlm"],
                )
                for col, _ in MEASURES
            ],
        )
    )
    report(selection, written)


if __name__ == "__main__":
    main()
