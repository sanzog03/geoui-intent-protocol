"""The generic deepeval suite: one app directory, one agent kind, the chosen datasets.

Run through the CLI (it calls the app's ``prepare()`` hook, writes run.json
and runs this file once per agent kind)::

    uv run python -m geouibench run benchmarks/<app> gold --run-id 2026-10-28-gold

or by hand, one agent kind per invocation (agents that share a browser must
never run in parallel, so no ``-n``)::

    BENCHMARK_APP=benchmarks/<app> BENCHMARK_AGENT=<kind> BENCHMARK_DATASET=gold BENCHMARK_RUN=<run-id> \\
    DEEPEVAL_RESULTS_FOLDER=benchmarks/<app>/results/<run-id>/deepeval \\
    uv run deepeval test run benchmarks/geouibench/evals/test_benchmark.py --identifier <run-id>-<kind>

Environment: ``BENCHMARK_APP`` (app directory), ``BENCHMARK_AGENT`` (one of
the app's agent kinds), ``BENCHMARK_DATASET`` (dataset names, comma
separated, or ``all``), ``BENCHMARK_RUN`` (results folder name),
``BENCHMARK_SMOKE=1`` (first golden of each dataset only, one extra user
turn), ``PLAYWRIGHT_CDP_ENDPOINT`` (passed to ``build_agent``). Every test
is synchronous on purpose: the simulator drives its own event loop and the
agent's clients live on it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from deepeval.dataset import ConversationalGolden
from dotenv import load_dotenv

from geouibench.apps import load_app_dir
from geouibench.datasets import goldens_for
from geouibench.harness import ConversationRunner
from geouibench.metrics import JUDGE_MODEL_NAME, judge_model
from geouibench.runner import ensure_run_info, run_golden

load_dotenv()
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

RUN = os.environ.get("BENCHMARK_RUN", "").strip()
APP_PATH = os.environ.get("BENCHMARK_APP", "").strip()
if not RUN or not APP_PATH:
    # Guard against plain `pytest` collecting this file: every test here spends real agent turns.
    pytest.skip(
        "live benchmark: set BENCHMARK_APP and BENCHMARK_RUN (use `python -m geouibench run`)", allow_module_level=True
    )

APP_DIR = load_app_dir(Path(APP_PATH))
APP = APP_DIR.app
AGENT = os.environ.get("BENCHMARK_AGENT", APP.agent_kinds[0]).strip()
if AGENT not in APP.agent_kinds:
    raise RuntimeError(f"BENCHMARK_AGENT must be one of {APP.agent_kinds}, got {AGENT!r}")
DATASET_ARG = os.environ.get("BENCHMARK_DATASET", "all").strip() or "all"
DATASETS = APP_DIR.select_datasets("all" if DATASET_ARG == "all" else [n.strip() for n in DATASET_ARG.split(",")])
SMOKE = os.environ.get("BENCHMARK_SMOKE", "").strip() not in ("", "0", "false")
RUN_DIR = APP_DIR.run_dir(RUN)
CDP_ENDPOINT = os.environ.get("PLAYWRIGHT_CDP_ENDPOINT") or None


def _cases() -> list[tuple[str, ConversationalGolden]]:
    cases: list[tuple[str, ConversationalGolden]] = []
    for name, path in DATASETS.items():
        goldens = goldens_for(path, AGENT, agent_kinds=APP.agent_kinds, default_budgets=APP.budgets)
        if SMOKE:
            goldens = goldens[:1]
        cases.extend((name, g) for g in goldens)
    return cases


CASES = _cases()
JUDGE = judge_model()


@pytest.fixture(scope="session")
def runner() -> ConversationRunner:
    """One runner (one agent kind) per process; the agent itself is built lazily inside the simulator's loop."""
    ensure_run_info(
        APP_DIR,
        RUN_DIR,
        run_name=RUN,
        datasets=DATASETS,
        judge_model=JUDGE_MODEL_NAME,
        extra={"smoke": SMOKE, "cdp_endpoint": CDP_ENDPOINT},
    )
    return ConversationRunner(APP, AGENT, run_dir=RUN_DIR, cdp_endpoint=CDP_ENDPOINT, dataset="", run_name=RUN)


@pytest.mark.integration
@pytest.mark.parametrize("dataset_name, golden", CASES, ids=[f"{name}-{g.name}[{AGENT}]" for name, g in CASES])
def test_conversation(runner: ConversationRunner, dataset_name: str, golden: ConversationalGolden) -> None:
    run_golden(runner, golden, dataset_name=dataset_name, judge=JUDGE, smoke=SMOKE)
