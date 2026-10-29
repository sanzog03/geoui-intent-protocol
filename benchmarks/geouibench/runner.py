"""One golden, one agent kind: simulate the conversation, score it, record it.

This is the loop the generic eval file (``geouibench/evals/test_benchmark.py``)
runs per test; it lives here so an application never writes it. deepeval's
``ConversationSimulator`` plays the user against
:class:`geouibench.harness.ConversationRunner`, ``assert_test`` scores the
conversation with :func:`geouibench.metrics.metrics_for`, and whatever
happened is appended to ``conversations.jsonl`` (a simulator failure is
recorded too, then re-raised so the test run shows it).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from deepeval import assert_test
from deepeval.dataset import ConversationalGolden
from deepeval.metrics import BaseConversationalMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.simulator import ConversationSimulator
from deepeval.test_case import ConversationalTestCase

from geouibench.appdir import AppDir
from geouibench.datasets import GoldenMeta, dataset_hash
from geouibench.deepeval_results import entries_from_current_test_run, metric_entry
from geouibench.harness import ConversationRecord, ConversationRunner, conversation_record
from geouibench.metrics import JUDGE_MODEL_NAME, metrics_for, state_reached_controller
from geouibench.records import append_record
from geouibench.run_dir import CONVERSATIONS, RUN_INFO, RunInfo, git_sha, package_versions, write_run_info

Evaluate = Callable[[ConversationalTestCase, Sequence[BaseConversationalMetric]], Any]


def ensure_run_info(
    app_dir: AppDir,
    run_dir: Path,
    *,
    run_name: str,
    datasets: dict[str, Path],
    judge_model: str = JUDGE_MODEL_NAME,
    extra: dict[str, Any] | None = None,
) -> RunInfo:
    """Write ``run.json`` once per run (the first agent's process writes it; later ones reuse it)."""
    run_dir = Path(run_dir)
    path = run_dir / RUN_INFO
    if path.exists():
        return RunInfo.model_validate_json(path.read_text(encoding="utf-8"))
    info = RunInfo(
        run_name=run_name,
        app=app_dir.relpath,
        reference_agent=app_dir.app.agent_kinds[0],
        agent_kinds=list(app_dir.app.agent_kinds),
        datasets={name: dataset_hash(p) for name, p in datasets.items()},
        judge_model=judge_model,
        git_sha=git_sha(),
        versions=package_versions("geouibench", "deepeval", "pydantic-ai", "geoui-protocol"),
        extra=extra or {},
    )
    write_run_info(run_dir, info)
    return info


def run_golden(
    runner: ConversationRunner,
    golden: ConversationalGolden,
    *,
    dataset_name: str,
    judge: DeepEvalBaseLLM | str | None,
    smoke: bool = False,
    simulator_factory: Callable[..., Any] = ConversationSimulator,
    metrics: Sequence[BaseConversationalMetric] | None = None,
    evaluate: Evaluate = assert_test,
) -> ConversationRecord:
    """Simulate ``golden`` against the runner's agent, score it, append the record; returns the record.

    ``simulator_factory``, ``metrics`` and ``evaluate`` exist so the loop can
    run offline in tests; a real run uses the defaults.
    """
    app = runner.app
    kind = runner.kind
    run_dir = runner.run_dir
    meta = GoldenMeta.model_validate(golden.additional_metadata or {})
    runner.dataset = dataset_name
    runner.start_golden(golden.name)
    name = f"{golden.name}[{kind}]"

    simulator_kwargs: dict[str, Any] = {"model_callback": runner.respond, "simulator_model": judge, "max_concurrent": 1}
    if meta.is_gold:  # goldens without an expected state keep deepeval's expected_outcome stop rule
        simulator_kwargs["stopping_controller"] = state_reached_controller(app)
    simulator = simulator_factory(**simulator_kwargs)
    extra_turns = 1 if smoke else meta.max_user_simulations
    try:
        test_case = simulator.simulate([golden], max_user_simulations=max(1, extra_turns))[0]
    except Exception as exc:
        record = ConversationRecord(
            name=name,
            agent=kind,
            dataset=dataset_name,
            run_name=runner.run_name,
            golden_name=golden.name,
            session_id=None,
            scenario=golden.scenario,
            expected_outcome=golden.expected_outcome,
            chatbot_role=app.chatbot_role(kind),
            turns=[],
            metadata={"simulator_error": f"{type(exc).__name__}: {exc}"},
        )
        append_record(record, run_dir / CONVERSATIONS)
        raise
    test_case.chatbot_role = app.chatbot_role(kind)
    test_case.name = name

    chosen = list(metrics) if metrics is not None else metrics_for(app, meta, judge)
    record: ConversationRecord | None = None
    try:
        evaluate(test_case, chosen)
    finally:
        record = conversation_record(
            test_case,
            agent=kind,
            dataset=dataset_name,
            run_name=runner.run_name,
            golden_name=golden.name,
            # deepeval scores copies of the metric objects; read its record, fall back to ours
            metrics=entries_from_current_test_run(name) or [metric_entry(m) for m in chosen],
        )
        append_record(record, run_dir / CONVERSATIONS)
    return record


__all__ = ["ensure_run_info", "run_golden"]
