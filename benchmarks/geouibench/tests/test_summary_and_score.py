"""A run directory produced offline by the runner can be summarised and re-scored."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from deepeval.test_case import ConversationalTestCase, Turn
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from geouibench.deepeval_results import metric_entry
from geouibench.harness import ConversationRunner, conversation_record
from geouibench.metrics import gold_metrics
from geouibench.run_dir import (
    SUMMARY_JSON,
    SUMMARY_MD,
    RunInfo,
    load_conversations,
    load_turns,
    read_run_info,
    scrub_run_dir,
    write_conversations,
    write_run_info,
)
from geouibench.score import load_app, merge_metrics, rebuild_test_case, score_run
from geouibench.summarize import summarize_run
from geouibench.summary import render_markdown, summarize
from geouibench.tests._fake_app import FakeApp, FakeOutput, fake_url

EXPECTED = {"layers": {"A": None}, "time": "2025-09-15"}
BUDGETS = {"seconds_per_turn": 60, "tokens_per_turn": 20000}


def _agent_factory(url: str, tool_calls: int):
    def factory(kind, caps):
        tools = FunctionToolset(id="t")

        @tools.tool_plain
        def lookup(q: str) -> str:
            """Look something up."""
            return "found"

        model = TestModel(
            custom_output_args={"result": "done", "url": url}, call_tools=["lookup"] if tool_calls else []
        )
        return Agent(model, name=f"a_{kind}", output_type=FakeOutput, toolsets=[tools], capabilities=list(caps))

    return factory


def _build_run(tmp_path: Path) -> Path:
    """Two agent kinds × one golden, scored with the deterministic metrics (no LLM)."""
    run_dir = tmp_path / "run"
    write_run_info(
        run_dir,
        RunInfo(
            run_name="r1",
            app="geouibench.tests._fake_app:FakeApp",
            reference_agent="x",
            agent_kinds=["x", "y"],
            judge_model="none",
        ),
    )
    conversations = []
    for kind, url, calls in (("x", fake_url("A", t="2025-09-15"), 1), ("y", fake_url("B", t="2025-09-15"), 1)):
        app = FakeApp(_agent_factory(url, calls))
        runner = ConversationRunner(app, kind, run_dir=run_dir, cdp_endpoint=None, dataset="gold", run_name="r1")
        runner.start_golden("g1")
        turn = asyncio.run(runner("render A", [], f"conv-{kind}"))
        tc = ConversationalTestCase(
            turns=[Turn(role="user", content="render A"), turn],
            scenario="s",
            expected_outcome="e",
            chatbot_role="role",
            name=f"g1[{kind}]",
            metadata={"expected_state": EXPECTED, "budgets": BUDGETS, "fully_specified": True, "agent_kind": kind},
        )
        metrics = [m for m in gold_metrics(app, model=None) if m.__name__ not in ("Completion", "Turn Relevancy")]
        for m in metrics:
            m.measure(tc)
        conversations.append(
            conversation_record(
                tc,
                agent=kind,
                dataset="gold",
                run_name="r1",
                golden_name="g1",
                metrics=[metric_entry(m) for m in metrics],
            )
        )
    write_conversations(run_dir, conversations)
    return run_dir


def test_summary_rows_ratios_and_totals(tmp_path):
    run_dir = _build_run(tmp_path)
    summary = summarize(load_conversations(run_dir), load_turns(run_dir), reference_agent="x", run_name="r1")
    assert [(r.golden, r.agent) for r in summary.rows] == [("g1", "x"), ("g1", "y")]
    x, y = summary.rows
    assert x.turns == 1 and x.tool_calls == 1 and x.seconds > 0 and x.total_tokens > 0
    assert x.metrics["Success"].score == 1.0 and x.metrics["Success"].success is True
    assert y.metrics["Success"].score == 0.5 and y.metrics["Success"].success is False
    assert summary.ratios["g1"]["y/x"]["tool_calls"] == 1.0
    assert summary.metric_names == ["Success", "Tool efficiency", "Time efficiency", "Token efficiency"]
    totals = {t.agent: t for t in summary.totals}
    assert totals["x"].pass_rate["Success"] == 1.0 and totals["y"].pass_rate["Success"] == 0.0
    assert totals["x"].conversations == 1 and totals["x"].mean_score["Tool efficiency"] == 1.0

    md = render_markdown(summary)
    assert "| g1 | x | 1.00 ✓" in md and "| g1 | y | 0.50 ✗" in md and "**y/x**" in md
    assert "## Per-agent totals" in md


def test_summarize_run_writes_files_and_scrubs_paths(tmp_path):
    run_dir = _build_run(tmp_path)
    (run_dir / "errors.jsonl").write_text(json.dumps({"traceback": "/Users/someone/x.py"}) + "\n")
    summary = summarize_run(run_dir)
    assert (run_dir / SUMMARY_JSON).exists() and (run_dir / SUMMARY_MD).exists()
    assert summary.run_name == "r1" and summary.reference_agent == "x"
    assert "/Users/" not in (run_dir / "errors.jsonl").read_text()
    assert scrub_run_dir(run_dir) == []  # idempotent


def test_offline_rescore_reproduces_the_deterministic_scores(tmp_path):
    run_dir = _build_run(tmp_path)
    before = {c.agent: {m["name"]: m["score"] for m in c.metrics} for c in load_conversations(run_dir)}
    # drop the recorded scores to prove they are recomputed, not copied
    stripped = [c.model_copy(update={"metrics": []}) for c in load_conversations(run_dir)]
    write_conversations(run_dir, stripped)

    records = score_run(run_dir, use_deepeval_evaluate=False)
    after = {c.agent: {m["name"]: m["score"] for m in c.metrics} for c in records}
    assert after == before
    assert read_run_info(run_dir).app == "geouibench.tests._fake_app:FakeApp"
    assert (run_dir / SUMMARY_MD).exists()


def test_rescore_through_deepeval_evaluate(tmp_path):
    run_dir = _build_run(tmp_path)
    records = score_run(run_dir, keys=("success", "tool"), use_deepeval_evaluate=True)
    scores = {c.agent: {m["name"]: m["score"] for m in c.metrics} for c in records}
    assert scores["x"]["Success"] == 1.0 and scores["y"]["Success"] == 0.5
    assert any((run_dir / "deepeval").glob("test_run_*.json"))


def test_rebuild_test_case_reattaches_traces(tmp_path):
    run_dir = _build_run(tmp_path)
    record = load_conversations(run_dir)[0]
    tc = rebuild_test_case(run_dir, record)
    assert tc.turns[1].metadata["trace"]["tool_calls"][0]["name"] == "lookup"
    assert tc.turns[1].tools_called[0].name == "lookup"
    assert tc.name == "g1[x]" and tc.chatbot_role == "role"


def test_load_app_and_merge_metrics():
    assert isinstance(load_app("geouibench.tests._fake_app:FakeApp"), FakeApp)
    merged = merge_metrics([{"name": "A", "score": 0.1}, {"name": "B", "score": 0.2}], [{"name": "A", "score": 0.9}])
    assert merged == [{"name": "A", "score": 0.9}, {"name": "B", "score": 0.2}]
