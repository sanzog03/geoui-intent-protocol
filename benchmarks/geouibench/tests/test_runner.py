"""run_golden drives simulate → score → record, offline, with a stand-in simulator and no LLM."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from deepeval.dataset import ConversationalGolden
from deepeval.test_case import ConversationalTestCase, Turn
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from geouibench.appdir import load_app_dir
from geouibench.harness import ConversationRunner
from geouibench.metrics import deterministic_only, gold_metrics
from geouibench.run_dir import load_conversations, load_turns, read_run_info
from geouibench.runner import ensure_run_info, run_golden
from geouibench.tests._fake_app import FakeApp, FakeOutput, fake_url
from geouibench.tests.test_appdir import make_app_dir

GOLDEN = ConversationalGolden(
    name="g1",
    scenario="Render A on 2025-09-15.",
    expected_outcome="A shown.",
    turns=[Turn(role="user", content="render A")],
    additional_metadata={
        "expected_state": {"layers": {"A": None}, "time": "2025-09-15"},
        "budgets": {"seconds_per_turn": 60, "tokens_per_turn": 20000},
        "fully_specified": True,
        "max_user_simulations": 0,
        "agent_kind": "x",
    },
)


class StubSimulator:
    """Plays one user turn (the opener) through the callback, like deepeval's simulator would."""

    def __init__(self, *, model_callback, simulator_model, max_concurrent, stopping_controller=None):
        self.callback = model_callback
        self.controller = stopping_controller

    def simulate(self, goldens, max_user_simulations):
        golden = goldens[0]
        opener = golden.turns[0]
        reply = asyncio.run(self.callback(opener.content, [opener], f"thread-{golden.name}"))
        return [
            ConversationalTestCase(
                turns=[opener, reply],
                scenario=golden.scenario,
                expected_outcome=golden.expected_outcome,
                additional_metadata=golden.additional_metadata,
            )
        ]


class FailingSimulator(StubSimulator):
    def simulate(self, goldens, max_user_simulations):
        raise RuntimeError("simulator model unreachable")


def _measure_all(test_case, metrics):
    for m in metrics:
        m.measure(test_case)


def _factory(kind, caps):
    model = TestModel(custom_output_args={"result": "done", "url": fake_url("A", t="2025-09-15")})
    return Agent(model, name=f"a_{kind}", output_type=FakeOutput, capabilities=list(caps))


@pytest.fixture
def runner(tmp_path: Path) -> ConversationRunner:
    app = FakeApp(_factory)
    return ConversationRunner(app, "x", run_dir=tmp_path / "run", cdp_endpoint=None, dataset="", run_name="r1")


def test_run_golden_records_the_conversation_with_scores(runner):
    metrics = deterministic_only(gold_metrics(runner.app, None))
    record = run_golden(
        runner,
        GOLDEN,
        dataset_name="gold",
        judge=None,
        simulator_factory=StubSimulator,
        metrics=metrics,
        evaluate=_measure_all,
    )
    assert record.name == "g1[x]" and record.agent == "x" and record.dataset == "gold"
    assert record.chatbot_role == "A fake x assistant."
    assert [t["role"] for t in record.turns] == ["user", "assistant"]
    scores = {m["name"]: m["score"] for m in record.metrics}
    assert scores["Success"] == 1.0 and scores["Tool efficiency"] == 1.0
    assert "trace" not in (record.turns[1]["metadata"] or {}) and record.turns[1]["metadata"]["trace_path"]
    assert load_conversations(runner.run_dir) == [record]
    assert len(load_turns(runner.run_dir)) == 1 and load_turns(runner.run_dir)[0].golden_name == "g1"


def test_run_golden_records_a_simulator_failure_and_reraises(runner):
    with pytest.raises(RuntimeError, match="simulator model unreachable"):
        run_golden(runner, GOLDEN, dataset_name="gold", judge=None, simulator_factory=FailingSimulator)
    [record] = load_conversations(runner.run_dir)
    assert record.turns == [] and record.session_id is None
    assert record.metadata["simulator_error"].startswith("RuntimeError:")


def test_run_golden_records_even_when_a_metric_threshold_fails(runner):
    class Fail(Exception):
        pass

    def strict(test_case, metrics):
        _measure_all(test_case, metrics)
        raise Fail("below threshold")

    with pytest.raises(Fail):
        run_golden(
            runner,
            GOLDEN,
            dataset_name="gold",
            judge=None,
            simulator_factory=StubSimulator,
            metrics=deterministic_only(gold_metrics(runner.app, None)),
            evaluate=strict,
        )
    assert len(load_conversations(runner.run_dir)) == 1


def test_stub_simulator_gets_the_stopping_controller_for_gold_only(runner):
    seen = {}

    class Spy(StubSimulator):
        def __init__(self, **kw):
            seen.update(kw)
            super().__init__(**kw)

    run_golden(
        runner, GOLDEN, dataset_name="gold", judge=None, simulator_factory=Spy, metrics=[], evaluate=_measure_all
    )
    assert seen["model_callback"] == runner.respond and seen["stopping_controller"] is not None
    synthetic = GOLDEN.model_copy(update={"additional_metadata": {"budgets": GOLDEN.additional_metadata["budgets"]}})
    seen.clear()
    run_golden(
        runner, synthetic, dataset_name="syn", judge=None, simulator_factory=Spy, metrics=[], evaluate=_measure_all
    )
    assert "stopping_controller" not in seen


def test_ensure_run_info_writes_once(tmp_path):
    app_dir = load_app_dir(make_app_dir(tmp_path, datasets={"gold_dataset": []}))
    run_dir = app_dir.run_dir("r1")
    info = ensure_run_info(app_dir, run_dir, run_name="r1", datasets=app_dir.select_datasets("gold"), extra={"a": 1})
    assert info.reference_agent == "x" and info.agent_kinds == ["x", "y"] and "gold" in info.datasets
    assert info.app == app_dir.relpath and "geouibench" in info.versions
    again = ensure_run_info(app_dir, run_dir, run_name="other", datasets={})
    assert again == info == read_run_info(run_dir)
