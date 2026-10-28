"""The six metrics and the stopping rule, on hand-built conversations with traces."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from deepeval.dataset import ConversationalGolden
from deepeval.test_case import ConversationalTestCase, Turn

from geobench.metrics import (
    CompletionMetric,
    SuccessMetric,
    TimeEfficiencyMetric,
    TokenEfficiencyMetric,
    ToolEfficiencyMetric,
    deterministic_only,
    gold_metrics,
    state_reached_controller,
    synthetic_metrics,
)
from geobench.records import TurnUsage
from geobench.tests._fake_app import FakeApp, fake_url
from geobench.tracing import LLMCall, ToolCallRecord, TurnTrace

APP = FakeApp()
BUDGETS = {"seconds_per_turn": 10, "tokens_per_turn": 1000}


def trace(
    *tools: tuple[str, dict[str, Any] | None, str | None],
    seconds: float = 5.0,
    tokens: tuple[int, int, int] = (800, 100, 0),
) -> TurnTrace:
    """A TurnTrace with ``tools`` = (name, args, error) and ``tokens`` = (input, output, cache_read)."""
    inp, out, cache = tokens
    return TurnTrace(
        trace_id="t",
        started_at=datetime.now(UTC).isoformat(),
        duration_s=seconds,
        llm_calls=[LLMCall(model="m", input_tokens=inp, output_tokens=out, duration_s=1.0, offset_s=0.0)],
        tool_calls=[
            ToolCallRecord(name=n, args=a, output="o", duration_s=0.1, offset_s=0.0, error=e) for n, a, e in tools
        ],
        usage=TurnUsage(input_tokens=inp, output_tokens=out, cache_read_tokens=cache, requests=1),
    )


def assistant(content: str, *, url: str | None, tr: TurnTrace | None, kind: str = "structured") -> Turn:
    meta: dict[str, Any] = {"output_kind": kind, "final_url": url}
    if tr is not None:
        meta["trace"] = tr.model_dump(mode="json")
    return Turn(role="assistant", content=content, metadata=meta)


def case(turns: list[Turn], **meta: Any) -> ConversationalTestCase:
    metadata = {"budgets": BUDGETS, **meta}
    return ConversationalTestCase(turns=turns, scenario="s", expected_outcome="e", metadata=metadata)


EXPECTED = {"layers": {"A": None}, "time": "2025-09-15"}


def test_success_uses_the_last_url_and_the_goldens_threshold():
    turns = [
        Turn(role="user", content="go"),
        assistant("done", url=fake_url("A", t="2025-09-14"), tr=trace()),
        Turn(role="user", content="next day"),
        assistant("done", url=fake_url("A", t="2025-09-15"), tr=trace()),
    ]
    metric = SuccessMetric(APP)
    assert metric.measure(case(turns, expected_state=EXPECTED)) == 1.0
    assert metric.is_successful() and metric.threshold == 1.0

    partial = SuccessMetric(APP)
    partial.measure(case(turns[:2], expected_state=EXPECTED, state_threshold=0.5))
    assert partial.score == 0.5 and partial.is_successful() and "missed ['time']" in partial.reason

    strict = SuccessMetric(APP)
    strict.measure(case(turns[:2], expected_state=EXPECTED))
    assert strict.score == 0.5 and not strict.is_successful()


def test_success_with_no_url_scores_zero():
    metric = SuccessMetric(APP)
    assert metric.measure(case([assistant("hm?", url=None, tr=None, kind="text")], expected_state=EXPECTED)) == 0.0
    assert "no URL" in metric.reason


def test_success_errors_without_expected_state():
    metric = SuccessMetric(APP)
    metric.measure(case([assistant("x", url=fake_url("A"), tr=trace())]))
    assert metric.is_successful() is False and metric.error


class _FakeInner:
    def __init__(self, score: float):
        self.score, self.reason, self.evaluation_cost = score, "llm says so", 0.01

    def measure(self, test_case, *a, **k):
        return self.score

    async def a_measure(self, test_case, *a, **k):
        return self.score


def test_completion_averages_checkpoints_with_the_llm_score():
    turns = [
        assistant("1", url=fake_url("A", t="2025-09-14"), tr=trace()),
        assistant("2", url=fake_url("A", t="2025-09-15"), tr=trace()),
    ]
    checkpoints = [{"time": "2025-09-14"}, {"time": "2025-09-15"}, {"layers": {"Z": None}}]
    metric = CompletionMetric(APP, model=None)
    metric.inner = _FakeInner(0.9)
    score = asyncio.run(metric.a_measure(case(turns, expected_state=EXPECTED, checkpoints=checkpoints)))
    assert score == pytest.approx((2 / 3 + 0.9) / 2, abs=1e-4)
    assert metric.score_breakdown["checkpoints_reached"] == [0, 1]
    assert metric.is_successful()

    synthetic = CompletionMetric(APP, model=None)
    synthetic.inner = _FakeInner(0.6)
    assert synthetic.measure(case(turns)) == 0.6 and not synthetic.is_successful()


def test_tool_efficiency_counts_waste_by_reason():
    first = trace(("render", {"a": 1}, None), ("navigate", {"u": "x"}, None))
    second = trace(("render", {"a": 1}, None), ("search", {"q": "aod"}, None), ("navigate", {"u": "y"}, "timeout"))
    turns = [
        assistant("1", url=fake_url("A"), tr=first),
        assistant("2", url=fake_url("A"), tr=second),
        assistant("boom", url=None, tr=None, kind="error"),
    ]
    metric = ToolEfficiencyMetric(APP)
    score = metric.measure(case(turns, expected_state=EXPECTED, fully_specified=True))
    # 5 tool calls + 1 error turn = 6 total; wasted: 1 duplicate render, 1 errored, 1 discovery, 1 error turn
    assert metric.score_breakdown["total"] == 6
    assert metric.score_breakdown["wasted"] == {"duplicate": 1, "errored": 1, "discovery": 1, "error_turn": 1}
    assert score == pytest.approx(1 - 4 / 6, abs=1e-4)
    assert not metric.is_successful()

    relaxed = ToolEfficiencyMetric(APP)
    relaxed.measure(case(turns[:2], expected_state=EXPECTED, fully_specified=False))
    assert relaxed.score_breakdown["wasted"]["discovery"] == 0

    empty = ToolEfficiencyMetric(APP)
    assert empty.measure(case([assistant("hi", url=None, tr=trace(), kind="text")])) == 1.0


def test_time_efficiency_scales_with_the_budget():
    within = TimeEfficiencyMetric()
    assert within.measure(case([assistant("1", url=None, tr=trace(seconds=8))])) == 1.0
    over = TimeEfficiencyMetric()
    assert over.measure(case([assistant("1", url=None, tr=trace(seconds=40))])) == 0.25
    assert not over.is_successful() and over.score_breakdown["mean_s"] == 40
    fallback = TimeEfficiencyMetric()
    fallback.measure(case([Turn(role="assistant", content="x", metadata={"output_kind": "error", "wall_clock_s": 20})]))
    assert fallback.score == 0.5


def test_token_efficiency_uses_cache_adjusted_tokens_from_the_trace():
    # input 2000, output 100, cache_read 1500 → 2000 - 1500 + 150 + 100 = 750 ≤ 1000 budget
    within = TokenEfficiencyMetric()
    assert within.measure(case([assistant("1", url=None, tr=trace(tokens=(2000, 100, 1500)))])) == 1.0
    over = TokenEfficiencyMetric()
    assert over.measure(case([assistant("1", url=None, tr=trace(tokens=(3900, 100, 0)))])) == 0.25
    assert over.score_breakdown["input_tokens"] == 3900 and over.score_breakdown["requests"] == 1


def test_missing_budgets_is_an_error():
    metric = TimeEfficiencyMetric()
    tc = ConversationalTestCase(turns=[assistant("1", url=None, tr=trace())], metadata={})
    metric.measure(tc)
    assert metric.is_successful() is False and "budgets" in metric.error


def test_metric_sets_are_fresh_instances():
    gold = gold_metrics(APP, model=None)
    assert [m.__name__ for m in gold] == [
        "Success",
        "Completion",
        "Tool efficiency",
        "Time efficiency",
        "Token efficiency",
        "Turn Relevancy",
    ]
    assert len(synthetic_metrics(APP, model=None)) == 5
    assert gold[0] is not gold_metrics(APP, model=None)[0]
    assert [m.__name__ for m in deterministic_only(gold)] == [
        "Success",
        "Tool efficiency",
        "Time efficiency",
        "Token efficiency",
    ]


def test_metrics_survive_deepevals_per_test_case_copy():
    from deepeval.metrics.utils.metrics import copy_metrics

    originals = gold_metrics(APP, model=None)
    copies = copy_metrics(originals)
    assert [type(c) for c in copies] == [type(o) for o in originals]
    assert all(c is not o for c, o in zip(copies, originals, strict=True))
    assert copies[0].app is APP and copies[2].threshold == originals[2].threshold


def _golden(**meta: Any) -> ConversationalGolden:
    return ConversationalGolden(scenario="s", additional_metadata=meta)


def test_controller_proceeds_before_any_assistant_turn():
    ctl = state_reached_controller(APP)
    decision = ctl(
        turns=[Turn(role="user", content="hi")], golden=_golden(), last_assistant_turn=None, simulated_user_turns=0
    )
    assert not decision.should_end


def test_controller_ends_when_the_state_is_reached():
    ctl = state_reached_controller(APP)
    done = assistant("done", url=fake_url("A", t="2025-09-15"), tr=None)
    golden = _golden(expected_state=EXPECTED, max_user_simulations=3)
    decision = ctl(
        turns=[Turn(role="user", content="go"), done], golden=golden, last_assistant_turn=done, simulated_user_turns=0
    )
    assert decision.should_end and "reached" in decision.reason


def test_controller_proceeds_until_checkpoints_are_hit_then_ends():
    ctl = state_reached_controller(APP)
    golden = _golden(expected_state=EXPECTED, checkpoints=[{"time": "2025-09-14"}], max_user_simulations=3)
    final = assistant("done", url=fake_url("A", t="2025-09-15"), tr=None)
    assert not ctl(turns=[final], golden=golden, last_assistant_turn=final, simulated_user_turns=1).should_end
    earlier = assistant("day before", url=fake_url("A", t="2025-09-14"), tr=None)
    assert ctl(turns=[earlier, final], golden=golden, last_assistant_turn=final, simulated_user_turns=1).should_end


def test_controller_enforces_the_goldens_cap_even_when_not_reached():
    ctl = state_reached_controller(APP)
    wrong = assistant("nope", url=fake_url("B"), tr=None)
    golden = _golden(expected_state=EXPECTED, max_user_simulations=0)
    assert ctl(turns=[wrong], golden=golden, last_assistant_turn=wrong, simulated_user_turns=0).should_end
    golden2 = _golden(expected_state=EXPECTED, max_user_simulations=2)
    assert not ctl(turns=[wrong], golden=golden2, last_assistant_turn=wrong, simulated_user_turns=1).should_end
    text_only = assistant("which layer?", url=None, tr=None, kind="text")
    assert not ctl(turns=[text_only], golden=golden2, last_assistant_turn=text_only, simulated_user_turns=0).should_end
