"""``python -m geobench.score <run dir>``: recompute the metrics from committed traces and transcripts.

No agent, no browser. Each conversation in ``conversations.jsonl`` is
rebuilt as a deepeval ``ConversationalTestCase`` with its saved
``TurnTrace`` re-attached, and the chosen metrics run through
``deepeval.evaluate``. The deterministic four need no network; Completion
and Turn relevancy call the judge model again. Scores replace the
same-named entries in ``conversations.jsonl`` and the summary is rewritten.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

from deepeval import evaluate
from deepeval.evaluate.configs import AsyncConfig, DisplayConfig, ErrorConfig
from deepeval.test_case import ConversationalTestCase, ToolCall, Turn

from geobench.app import BenchmarkApp
from geobench.datasets import GoldenMeta
from geobench.deepeval_results import metric_entry, metric_entry_from_data
from geobench.harness import ConversationRecord
from geobench.metrics import deterministic_only, judge_model, metrics_for
from geobench.run_dir import DEEPEVAL_DIR, load_conversations, read_run_info, write_conversations
from geobench.summarize import summarize_run
from geobench.tracing import load_trace

METRIC_KEYS = {
    "success": "Success",
    "completion": "Completion",
    "tool": "Tool efficiency",
    "time": "Time efficiency",
    "token": "Token efficiency",
    "relevancy": "Turn Relevancy",
}
DETERMINISTIC_KEYS = ("success", "tool", "time", "token")


def load_app(path: str) -> BenchmarkApp:
    """``'module:Class'`` → an instance."""
    module_name, _, attr = path.partition(":")
    if not attr:
        raise ValueError(f"app path must be 'module:Class', got {path!r}")
    cls = getattr(importlib.import_module(module_name), attr)
    return cls()


def rebuild_test_case(run_dir: Path, record: ConversationRecord) -> ConversationalTestCase:
    """Rebuild the simulator's test case; traces are loaded from ``trace_path`` and re-attached inline."""
    turns: list[Turn] = []
    for t in record.turns:
        meta = dict(t.get("metadata") or {})
        trace_path = meta.get("trace_path")
        if trace_path:
            meta["trace"] = load_trace(Path(run_dir) / trace_path).model_dump(mode="json")
        turns.append(
            Turn(
                role=t["role"],
                content=t["content"],
                tools_called=[ToolCall(**tc) for tc in t.get("tools_called") or []] or None,
                metadata=meta or None,
            )
        )
    return ConversationalTestCase(
        turns=turns,
        scenario=record.scenario,
        expected_outcome=record.expected_outcome,
        chatbot_role=record.chatbot_role,
        name=record.name,
        metadata=record.metadata,
    )


def merge_metrics(existing: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {m["name"]: m for m in existing if "name" in m}
    for m in new:
        by_name[m["name"]] = m
    return list(by_name.values())


def score_run(
    run_dir: Path,
    *,
    keys: tuple[str, ...] = DETERMINISTIC_KEYS,
    model_name: str | None = None,
    app: BenchmarkApp | None = None,
    use_deepeval_evaluate: bool = True,
) -> list[ConversationRecord]:
    run_dir = Path(run_dir)
    info = read_run_info(run_dir)
    app = app or load_app(info.app)
    wanted = {METRIC_KEYS[k] for k in keys}
    needs_llm = wanted - {METRIC_KEYS[k] for k in DETERMINISTIC_KEYS}
    model = judge_model(model_name or info.judge_model) if needs_llm else None

    conversations = load_conversations(run_dir)
    updated: list[ConversationRecord] = []
    for record in conversations:
        test_case = rebuild_test_case(run_dir, record)
        meta = GoldenMeta.model_validate(record.metadata or {})
        metrics = [m for m in metrics_for(app, meta, model) if m.__name__ in wanted]
        if not needs_llm:
            metrics = deterministic_only(metrics)
        if not metrics:
            updated.append(record)
            continue
        if use_deepeval_evaluate:
            result = evaluate(
                [test_case],
                metrics,
                identifier=f"{info.run_name}-rescore",
                async_config=AsyncConfig(run_async=False),
                display_config=DisplayConfig(
                    show_indicator=False,
                    print_results=False,
                    results_folder=str(run_dir / DEEPEVAL_DIR),
                    inspect_after_run=False,
                ),
                error_config=ErrorConfig(ignore_errors=True),
            )
            # deepeval may score copies of the metric objects; read the results it returns
            data = result.test_results[0].metrics_data if result.test_results else None
            entries = [metric_entry_from_data(m) for m in data] if data else [metric_entry(m) for m in metrics]
        else:
            for metric in metrics:
                metric.measure(test_case)
            entries = [metric_entry(m) for m in metrics]
        updated.append(record.model_copy(update={"metrics": merge_metrics(record.metrics, entries)}))
    write_conversations(run_dir, updated)
    summarize_run(run_dir)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--metrics",
        default=",".join(DETERMINISTIC_KEYS),
        help=f"comma-separated subset of {', '.join(METRIC_KEYS)} or 'all' (default: the deterministic four)",
    )
    parser.add_argument("--model", help="judge model for the LLM metrics (default: run.json)")
    args = parser.parse_args(argv)
    keys = (
        tuple(METRIC_KEYS) if args.metrics == "all" else tuple(k.strip() for k in args.metrics.split(",") if k.strip())
    )
    unknown = [k for k in keys if k not in METRIC_KEYS]
    if unknown:
        parser.error(f"unknown metrics {unknown}; choose from {', '.join(METRIC_KEYS)}")
    records = score_run(args.run_dir, keys=keys, model_name=args.model)
    print(f"re-scored {len(records)} conversations in {args.run_dir} for {[METRIC_KEYS[k] for k in keys]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
