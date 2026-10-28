"""``python -m geobench.summarize <run dir>``: write ``summary.json`` and ``summary.md`` for a run.

Also scrubs machine-specific absolute paths out of every text artifact in
the run directory, so the folder can be committed as is.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from geobench.run_dir import (
    SUMMARY_JSON,
    SUMMARY_MD,
    load_conversations,
    load_turns,
    read_run_info,
    scrub_run_dir,
)
from geobench.summary import Summary, render_markdown, summarize


def summarize_run(run_dir: Path, *, reference_agent: str | None = None) -> Summary:
    run_dir = Path(run_dir)
    info = read_run_info(run_dir)
    summary = summarize(
        load_conversations(run_dir),
        load_turns(run_dir),
        reference_agent=reference_agent or info.reference_agent,
        run_name=info.run_name,
    )
    (run_dir / SUMMARY_JSON).write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / SUMMARY_MD).write_text(render_markdown(summary), encoding="utf-8")
    scrub_run_dir(run_dir)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--reference", help="agent kind the ratios are relative to (default: run.json)")
    args = parser.parse_args(argv)
    summary = summarize_run(args.run_dir, reference_agent=args.reference)
    print(render_markdown(summary))
    print(f"wrote {args.run_dir / SUMMARY_JSON} and {args.run_dir / SUMMARY_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
