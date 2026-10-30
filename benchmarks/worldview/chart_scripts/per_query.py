# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9"]
# ///
"""Per query, GeoUI vs VLM: one measure for every query, side by side (log scale).

One pair of horizontal bars per query, sorted by the VLM / GeoUI ratio; the
ratio is printed at the end of each pair and a cross marks a conversation the
agent got wrong, so the cost of a failure is visible next to its size.

    uv run benchmarks/worldview/chart_scripts/per_query.py                            # tool calls
    uv run benchmarks/worldview/chart_scripts/per_query.py --measure seconds
    uv run benchmarks/worldview/chart_scripts/per_query.py --measure cache_adjusted_tokens --set gold

Writes per_query-<measure>-<set>.png/.svg/.csv under <run>/charts/.
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
    human,
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

MEASURES = {
    "tool_calls": "Tool calls",
    "seconds": "Agent seconds",
    "cache_adjusted_tokens": "Cache-adjusted tokens",
    "total_tokens": "Total tokens",
    "llm_requests": "LLM requests",
    "cost_usd": "Cost (USD)",
}


def main() -> None:
    p = parser(__doc__.splitlines()[0])
    p.add_argument("--measure", choices=sorted(MEASURES), default="tool_calls")
    args = p.parse_args()
    sel = select(read_rows(args.run), set_name=args.set_name, paired=args.paired, correct_only=args.correct_only)
    by_query: dict[str, dict[str, dict]] = {}
    for r in sel.rows:
        by_query.setdefault(r["golden"], {})[r["agent"]] = r

    def r_of(q: str) -> float:
        g = by_query[q].get("geoui", {}).get(args.measure)
        v = by_query[q].get("vlm", {}).get(args.measure)
        return ratio(v, g) or 0.0

    queries = sorted(by_query, key=r_of)
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(12, 0.42 * len(queries) + 2.2))
    height = 0.38
    numbers = []
    for qi, q in enumerate(queries):
        for ai, agent in enumerate(AGENTS):
            row = by_query[q].get(agent)
            if row is None:
                continue
            value = row.get(args.measure) or 0
            y = qi + (ai - 0.5) * (height + 0.03)
            ax.barh(y, max(value, 1e-9), height, color=AGENT_COLOR[agent], hatch=AGENT_HATCH[agent],
                    edgecolor="white", linewidth=0, label=AGENT_LABEL[agent] if qi == 0 else None)  # fmt: skip
            mark = "" if row.get("correct") else "  ✗ wrong"
            ax.text(max(value, 1), y, f" {human(value) if args.measure != 'cost_usd' else f'${value:.2f}'}{mark}",
                    va="center", fontsize=8.5, color=INK)  # fmt: skip
        g = by_query[q].get("geoui", {}).get(args.measure)
        v = by_query[q].get("vlm", {}).get(args.measure)
        numbers.append((q, by_query[q]["geoui"]["golden_kind"], g, v, ratio(v, g),
                        by_query[q]["geoui"].get("correct"), by_query[q]["vlm"].get("correct")))  # fmt: skip
    ax.set_xscale("log")
    ax.set_yticks(range(len(queries)))
    ax.set_yticklabels([f"{q}  ({times(r_of(q))})" for q in queries], fontsize=9.5)
    ax.grid(axis="x", which="major", color=GRID)
    ax.set_axisbelow(True)
    ax.set_xlabel(f"{MEASURES[args.measure]} per conversation (log scale)")
    ax.legend(loc="lower right", frameon=False, handlelength=2.5, handleheight=1.4)
    lo = min((n[2] or 1) for n in numbers if n[2]) if numbers else 1
    hi = max((n[3] or 1) for n in numbers) if numbers else 10
    ax.set_xlim(max(lo / 3, 1e-3), hi * 8)
    ax.set_title(
        f"GeoUI vs VLM — {MEASURES[args.measure].lower()} per query, sorted by VLM / GeoUI ratio",
        fontsize=13, fontweight="bold", color=INK, loc="left",
    )  # fmt: skip
    fig.text(0.01, 0.005, sel.footnote("Ratio in brackets = VLM / GeoUI. ✗ = conversation judged wrong."),
             fontsize=8.5, color=INK_MUTED, style="italic")  # fmt: skip
    fig.tight_layout(rect=(0, 0.03, 1, 1))

    stem = output_stem(args, f"per_query-{args.measure}")
    written = save(fig, stem)
    written.append(
        write_numbers(stem, ["query", "set", "geoui", "vlm", "vlm_over_geoui", "geoui_correct", "vlm_correct"], numbers)
    )
    report(sel, written)


if __name__ == "__main__":
    main()
