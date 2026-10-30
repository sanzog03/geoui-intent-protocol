# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9"]
# ///
"""Render every chart for one run into <run>/charts/.

    uv run benchmarks/worldview/chart_scripts/make_all.py
    uv run benchmarks/worldview/chart_scripts/make_all.py --run benchmarks/worldview/results/<run-id>

Each chart is its own script; this only calls them in turn with the variants
worth having on a slide. Every image has a .csv of the plotted numbers beside it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import DEFAULT_RUN

HERE = Path(__file__).resolve().parent

JOBS = [
    ["cost_per_task.py"],
    ["cost_per_task.py", "--set", "gold"],
    ["cost_per_task.py", "--set", "synthetic"],
    ["cost_per_task.py", "--correct-only"],
    ["time_per_task.py"],
    ["time_per_task.py", "--correct-only"],
    ["correctness.py"],
    ["per_query.py", "--measure", "tool_calls"],
    ["per_query.py", "--measure", "seconds"],
    ["per_query.py", "--measure", "cache_adjusted_tokens"],
    ["per_query.py", "--measure", "cost_usd"],
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, default=DEFAULT_RUN)
    args = p.parse_args()
    status = 0
    for job in JOBS:
        print(f"\n$ {' '.join(job)}")
        rc = subprocess.run(
            [sys.executable, str(HERE / job[0]), *job[1:], "--run", str(args.run)], check=False
        ).returncode
        status = status or rc
    return status


if __name__ == "__main__":
    raise SystemExit(main())
