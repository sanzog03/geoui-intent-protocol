"""``python -m geouibench``: run, score, summarize and generate for any app directory.

::

    python -m geouibench run       <app dir> <dataset>... [--run-id ID] [--agent KIND ...] [--smoke]
    python -m geouibench score     <run dir> [--metrics all|success,tool,...] [--model NAME]
    python -m geouibench summarize <run dir> [--reference KIND]
    python -m geouibench synthetic <app dir> [--gold NAME] [--out NAME] [--model NAME]
    python -m geouibench datasets  <app dir>

``run`` loads ``<app dir>/app.py``, calls the app's optional ``prepare()``
hook (browser, warm-ups, prerequisite checks), writes ``run.json``, then
runs ``deepeval test run`` on the generic eval file once per agent kind,
sequentially, with the results folder under ``<app dir>/results/<run-id>/``,
and finally writes the summary. Agent kinds run one after another on
purpose: agents of one app may share a browser.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from geouibench.app import prepare_app
from geouibench.apps import AppDir, load_app_dir
from geouibench.metrics import JUDGE_MODEL_NAME
from geouibench.run_dir import DEEPEVAL_DIR
from geouibench.runner import ensure_run_info
from geouibench.score import DETERMINISTIC_KEYS, METRIC_KEYS, score_run
from geouibench.summarize import summarize_run
from geouibench.summary import render_markdown
from geouibench.synthetic import SyntheticStyle, deepeval_executable, generate

EVAL_FILE = Path(__file__).resolve().parent / "evals" / "test_benchmark.py"

Spawn = Callable[..., Any]  # subprocess.run's shape: (cmd, *, env) -> object with .returncode


def default_run_id(dataset_names: list[str]) -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d") + "-" + "-".join(dataset_names)


def benchmark_env(
    app_dir: AppDir,
    *,
    run_id: str,
    dataset_names: list[str],
    smoke: bool,
    prepared: dict[str, str],
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """The environment of each ``deepeval test run`` process (the agent kind is added per process)."""
    env = dict(os.environ if base is None else base)
    env.update(prepared)
    env.update(
        {
            "DEEPEVAL_TELEMETRY_OPT_OUT": "YES",
            "DEEPEVAL_NO_INSPECT_PROMPT": "1",
            "BENCHMARK_APP": app_dir.relpath,
            "BENCHMARK_DATASET": ",".join(dataset_names),
            "BENCHMARK_RUN": run_id,
            "BENCHMARK_SMOKE": "1" if smoke else "",
            "DEEPEVAL_RESULTS_FOLDER": str(app_dir.run_dir(run_id) / DEEPEVAL_DIR),
        }
    )
    return env


def deepeval_test_run_command(run_id: str, agent: str) -> list[str]:
    return [
        deepeval_executable(),
        "test",
        "run",
        str(EVAL_FILE),
        "--identifier",
        f"{run_id}-{agent}",
        "--ignore-errors",
        "--display",
        "all",
    ]


def run_benchmark(
    app_dir: AppDir,
    dataset_names: list[str],
    *,
    run_id: str,
    agents: list[str] | None = None,
    smoke: bool = False,
    spawn: Spawn = subprocess.run,
    out=None,
) -> int:
    """The ``run`` subcommand; returns 1 when deepeval reported threshold failures for any agent, else 0."""
    out = out or sys.stdout
    app = app_dir.app
    datasets = app_dir.select_datasets(dataset_names)
    agents = list(agents or app.agent_kinds)
    unknown = [a for a in agents if a not in app.agent_kinds]
    if unknown:
        raise SystemExit(f"unknown agent kind(s) {unknown}; {app.name} has {app.agent_kinds}")
    run_dir = app_dir.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"App: {app.name} ({app_dir.relpath})  run: {run_id}  datasets: {', '.join(datasets)}", file=out)
    print(f"Agents: {', '.join(agents)}  smoke: {smoke}  results: {run_dir}", file=out)
    prepared = prepare_app(app)
    env = benchmark_env(app_dir, run_id=run_id, dataset_names=list(datasets), smoke=smoke, prepared=prepared, base=None)
    ensure_run_info(
        app_dir,
        run_dir,
        run_name=run_id,
        datasets=datasets,
        judge_model=JUDGE_MODEL_NAME,
        extra={"smoke": smoke, "cdp_endpoint": env.get("PLAYWRIGHT_CDP_ENDPOINT")},
    )

    status = 0
    for agent in agents:
        print(f"\n=== agent: {agent} ===", file=out)
        result = spawn(deepeval_test_run_command(run_id, agent), env={**env, "BENCHMARK_AGENT": agent})
        if result.returncode != 0:
            print(f"deepeval reported failures for {agent} (metric thresholds or errors); continuing", file=sys.stderr)
            status = 1

    summary = summarize_run(run_dir)
    print(file=out)
    print(render_markdown(summary), file=out)
    print(
        f"Done. Review and commit {run_dir} (summary.md, conversations.jsonl, turns.jsonl, traces/, deepeval/).",
        file=out,
    )
    return status


def run_synthetic(app_dir: AppDir, *, gold: str, out_name: str, model: str, work_dir: Path | None = None) -> Path:
    style = app_dir.synthetic_style
    if style is None:
        raise SystemExit(f"{app_dir.path}/app.py defines no SYNTHETIC_STYLE (a geouibench.synthetic.SyntheticStyle)")
    if not isinstance(style, SyntheticStyle):
        style = SyntheticStyle.model_validate(style)
    out_path = app_dir.datasets_dir / f"{out_name}.json"
    prepared = generate(style, gold_path=app_dir.dataset(gold), out_path=out_path, model=model, work_dir=work_dir)
    print(f"wrote {len(prepared)} goldens to {out_path}; review them, then commit")
    return out_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geouibench", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="simulate the datasets against every agent kind and summarise")
    run.add_argument("app_dir", type=Path)
    run.add_argument("datasets", nargs="+", help="dataset names under <app dir>/datasets, or 'all'")
    run.add_argument("--run-id", help="results folder name (default: <date>-<datasets>)")
    run.add_argument("--agent", action="append", help="agent kind to run (repeatable; default: all, in app order)")
    run.add_argument("--smoke", action="store_true", help="first golden of each dataset only, one extra user turn")

    score = sub.add_parser("score", help="recompute metrics from a run's committed traces and transcripts")
    score.add_argument("run_dir", type=Path)
    score.add_argument(
        "--metrics",
        default=",".join(DETERMINISTIC_KEYS),
        help=f"comma-separated subset of {', '.join(METRIC_KEYS)} or 'all' (default: the deterministic four)",
    )
    score.add_argument("--model", help="judge model for the LLM metrics (default: run.json)")

    summ = sub.add_parser("summarize", help="write summary.json and summary.md for a run")
    summ.add_argument("run_dir", type=Path)
    summ.add_argument("--reference", help="agent kind the ratios are relative to (default: run.json)")

    syn = sub.add_parser("synthetic", help="generate a synthetic dataset from a gold one with deepeval")
    syn.add_argument("app_dir", type=Path)
    syn.add_argument("--gold", default="gold", help="gold dataset name (default: gold)")
    syn.add_argument("--out", default="synthetic_queries", help="output dataset name (default: synthetic_queries)")
    syn.add_argument("--model", default=JUDGE_MODEL_NAME)
    syn.add_argument("--work-dir", type=Path, help="keep deepeval's intermediate files here")

    ds = sub.add_parser("datasets", help="list an app directory's datasets")
    ds.add_argument("app_dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    if args.command == "run":
        app_dir = load_app_dir(args.app_dir)
        names = app_dir.select_datasets(args.datasets)
        run_id = args.run_id or default_run_id(list(names))
        return run_benchmark(app_dir, args.datasets, run_id=run_id, agents=args.agent, smoke=args.smoke)
    if args.command == "score":
        keys = (
            tuple(METRIC_KEYS)
            if args.metrics == "all"
            else tuple(k.strip() for k in args.metrics.split(",") if k.strip())
        )
        unknown = [k for k in keys if k not in METRIC_KEYS]
        if unknown:
            raise SystemExit(f"unknown metrics {unknown}; choose from {', '.join(METRIC_KEYS)}")
        records = score_run(args.run_dir, keys=keys, model_name=args.model)
        print(f"re-scored {len(records)} conversations in {args.run_dir} for {[METRIC_KEYS[k] for k in keys]}")
        return 0
    if args.command == "summarize":
        summary = summarize_run(args.run_dir, reference_agent=args.reference)
        print(render_markdown(summary))
        return 0
    if args.command == "synthetic":
        run_synthetic(
            load_app_dir(args.app_dir), gold=args.gold, out_name=args.out, model=args.model, work_dir=args.work_dir
        )
        return 0
    if args.command == "datasets":
        for name, path in load_app_dir(args.app_dir).datasets().items():
            print(f"{name}\t{path}")
        return 0
    raise SystemExit(2)  # pragma: no cover


__all__ = [
    "EVAL_FILE",
    "benchmark_env",
    "build_parser",
    "deepeval_test_run_command",
    "default_run_id",
    "main",
    "run_benchmark",
    "run_synthetic",
]
