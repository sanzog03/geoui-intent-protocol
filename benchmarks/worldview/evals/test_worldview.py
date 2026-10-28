"""deepeval suite: the GeoUI and VLM Worldview agents on the same goldens, scored by the same metrics.

Run through the launcher (it brings up Chromium, warms the MCP servers and
writes run.json)::

    ./benchmarks/worldview/run.sh gold 2026-10-28-gold

or by hand, one agent per invocation (both agents share one Chromium tab,
so never pass ``-n``)::

    BENCHMARK_AGENT=geoui BENCHMARK_DATASET=gold BENCHMARK_RUN=2026-10-28-gold \\
    DEEPEVAL_RESULTS_FOLDER=benchmarks/worldview/results/2026-10-28-gold/deepeval \\
    uv run deepeval test run benchmarks/worldview/evals/test_worldview.py --identifier 2026-10-28-gold-geoui

Environment: ``BENCHMARK_AGENT`` (geoui | vlm), ``BENCHMARK_DATASET`` (gold |
synthetic | all), ``BENCHMARK_RUN`` (results folder name), ``BENCHMARK_SMOKE=1``
(first gold golden only, one extra user turn), ``PLAYWRIGHT_CDP_ENDPOINT``.
Every test is synchronous on purpose: the simulator drives its own event
loop and the agent's MCP clients live on it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.dataset import ConversationalGolden
from deepeval.simulator import ConversationSimulator
from dotenv import load_dotenv

from geobench.datasets import GoldenMeta, dataset_hash, goldens_for
from geobench.deepeval_results import entries_from_current_test_run, metric_entry
from geobench.harness import ConversationRunner, conversation_record
from geobench.metrics import JUDGE_MODEL_NAME, judge_model, metrics_for, state_reached_controller
from geobench.records import append_record
from geobench.run_dir import CONVERSATIONS, RUN_INFO, RunInfo, git_sha, package_versions, write_run_info
from worldview_benchmark import DEFAULT_BUDGETS, GOLD_DATASET, RESULTS_DIR, SYNTHETIC_DATASET
from worldview_benchmark.app import WorldviewApp

load_dotenv()
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

APP = WorldviewApp()
AGENT = os.environ.get("BENCHMARK_AGENT", "geoui").strip().lower()
DATASET = os.environ.get("BENCHMARK_DATASET", "gold").strip().lower()
RUN = os.environ.get("BENCHMARK_RUN", "").strip()
if not RUN:
    # Guard against `pytest benchmarks/worldview` collecting this file by accident: every test here
    # spends real agent turns. run.sh always sets BENCHMARK_RUN.
    pytest.skip("live benchmark: set BENCHMARK_RUN (use benchmarks/worldview/run.sh)", allow_module_level=True)
SMOKE = os.environ.get("BENCHMARK_SMOKE", "").strip() not in ("", "0", "false")
RUN_DIR = RESULTS_DIR / RUN
CDP_ENDPOINT = os.environ.get("PLAYWRIGHT_CDP_ENDPOINT") or None

if AGENT not in APP.agent_kinds:
    raise RuntimeError(f"BENCHMARK_AGENT must be one of {APP.agent_kinds}, got {AGENT!r}")

DATASETS: dict[str, Path] = {}
if DATASET in ("gold", "all"):
    DATASETS["gold"] = GOLD_DATASET
if DATASET in ("synthetic", "all"):
    if not SYNTHETIC_DATASET.exists():
        raise RuntimeError(f"{SYNTHETIC_DATASET} is missing; generate it first (see benchmarks/worldview/README.md)")
    DATASETS["synthetic"] = SYNTHETIC_DATASET
if not DATASETS:
    raise RuntimeError(f"BENCHMARK_DATASET must be gold, synthetic or all, got {DATASET!r}")


def _cases() -> list[tuple[str, ConversationalGolden]]:
    cases: list[tuple[str, ConversationalGolden]] = []
    for name, path in DATASETS.items():
        goldens = goldens_for(path, AGENT, agent_kinds=APP.agent_kinds, default_budgets=DEFAULT_BUDGETS)
        if SMOKE:
            goldens = goldens[:1]
        cases.extend((name, g) for g in goldens)
    return cases


CASES = _cases()
JUDGE = judge_model()


@pytest.fixture(scope="session")
def runner() -> ConversationRunner:
    """One runner (one agent) per process; the agent itself is built lazily inside the simulator's loop."""
    if not (RUN_DIR / RUN_INFO).exists():
        write_run_info(
            RUN_DIR,
            RunInfo(
                run_name=RUN,
                app="worldview_benchmark.app:WorldviewApp",
                reference_agent="geoui",
                agent_kinds=list(APP.agent_kinds),
                datasets={name: dataset_hash(path) for name, path in DATASETS.items()},
                judge_model=JUDGE_MODEL_NAME,
                git_sha=git_sha(),
                versions=package_versions("deepeval", "pydantic-ai", "fastmcp", "geoui-protocol"),
                extra={"smoke": SMOKE, "cdp_endpoint": CDP_ENDPOINT},
            ),
        )
    return ConversationRunner(
        APP,
        AGENT,
        run_dir=RUN_DIR,
        cdp_endpoint=CDP_ENDPOINT,
        dataset=DATASET,
        run_name=RUN,
    )


@pytest.mark.integration
@pytest.mark.parametrize("dataset_name, golden", CASES, ids=[f"{name}-{g.name}[{AGENT}]" for name, g in CASES])
def test_conversation(runner: ConversationRunner, dataset_name: str, golden: ConversationalGolden) -> None:
    meta = GoldenMeta.model_validate(golden.additional_metadata or {})
    runner.dataset = dataset_name
    runner.start_golden(golden.name)

    simulator_kwargs = {"model_callback": runner.respond, "simulator_model": JUDGE, "max_concurrent": 1}
    if meta.is_gold:  # synthetic goldens keep deepeval's expected_outcome stop rule
        simulator_kwargs["stopping_controller"] = state_reached_controller(APP)
    simulator = ConversationSimulator(**simulator_kwargs)
    extra_turns = 1 if SMOKE else meta.max_user_simulations
    test_case = simulator.simulate([golden], max_user_simulations=max(1, extra_turns))[0]
    test_case.chatbot_role = APP.chatbot_role(AGENT)
    test_case.name = f"{golden.name}[{AGENT}]"

    metrics = metrics_for(APP, meta, JUDGE)
    try:
        assert_test(test_case, metrics)
    finally:
        append_record(
            conversation_record(
                test_case,
                agent=AGENT,
                dataset=dataset_name,
                run_name=RUN,
                golden_name=golden.name,
                # deepeval scores copies of the metric objects; read its record, fall back to ours
                metrics=entries_from_current_test_run(test_case.name) or [metric_entry(m) for m in metrics],
            ),
            RUN_DIR / CONVERSATIONS,
        )
