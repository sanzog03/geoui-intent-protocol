"""The six benchmark metrics and the simulator's stopping rule.

The questions, in order: did the agent **succeed**, did it **complete** the
work, and while doing so how efficient was it in **tools**, **time** and
**tokens**, and were its turns **relevant**. One deepeval metric per
question. Four are deterministic and read their evidence from the
``TurnTrace`` attached to each assistant ``Turn`` (``metadata["trace"]``),
so the same classes score a live run and an offline re-score of committed
traces identically; two are LLM-judged by deepeval.

Nothing here knows which mechanism the agent uses: success is judged on the
UI state the application reads back, efficiency on the trace.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from deepeval.metrics import BaseConversationalMetric, ConversationCompletenessMetric, TurnRelevancyMetric
from deepeval.models import OpenAIModel
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.simulator.controller.controller import Decision, end, proceed
from deepeval.test_case import ConversationalTestCase, Turn

from geobench.app import BenchmarkApp
from geobench.datasets import Budgets, GoldenMeta
from geobench.records import TurnUsage
from geobench.state import checkpoint_reached, judge_url
from geobench.tracing import TurnTrace

#: The judge and simulated-user model, pinned in one place.
JUDGE_MODEL_NAME = "gpt-5.2"

COMPLETION_THRESHOLD = 0.7
TOOL_EFFICIENCY_THRESHOLD = 0.7
TIME_EFFICIENCY_THRESHOLD = 0.5
TOKEN_EFFICIENCY_THRESHOLD = 0.5
TURN_RELEVANCY_THRESHOLD = 0.7


def judge_model(name: str = JUDGE_MODEL_NAME) -> DeepEvalBaseLLM:
    return OpenAIModel(model=name)


# --- evidence access -------------------------------------------------------


def meta_of(test_case: ConversationalTestCase) -> GoldenMeta:
    """The golden's harness metadata, carried on the test case by the simulator."""
    return GoldenMeta.model_validate(test_case.metadata or {})


def trace_of(turn: Turn) -> TurnTrace | None:
    raw = (turn.metadata or {}).get("trace")
    if raw is None:
        return None
    return raw if isinstance(raw, TurnTrace) else TurnTrace.model_validate(raw)


def final_url_of(turn: Turn) -> str | None:
    return (turn.metadata or {}).get("final_url")


def assistant_turns(test_case: ConversationalTestCase) -> list[Turn]:
    return [t for t in test_case.turns if t.role == "assistant"]


def budgets_of(meta: GoldenMeta) -> Budgets | None:
    return meta.budgets


def observe_or_none(app: BenchmarkApp, url: str | None) -> Any:
    """The UI state at ``url``, or ``None`` when there is no URL or the app cannot parse it."""
    if not url:
        return None
    try:
        return app.observe(url)
    except Exception:  # noqa: BLE001 — an unparseable URL is "no judgeable state", not a crash
        return None


# --- deterministic metrics ------------------------------------------------


class _DeterministicMetric(BaseConversationalMetric):
    """No LLM: ``measure`` sets score / success / reason; ``a_measure`` delegates to it."""

    name = "Deterministic"
    evaluation_cost = None
    include_reason = True

    def __init__(self, threshold: float | None):
        self.threshold = threshold
        self.score = None
        self.success = None
        self.reason = None
        self.score_breakdown = None
        self.verbose_logs = None
        self.error = None

    def _finish(self, score: float, reason: str, breakdown: dict[str, Any] | None = None) -> float:
        self.score = round(score, 4)
        self.reason = reason
        self.score_breakdown = breakdown
        self.success = self.is_successful()
        return self.score

    def is_successful(self) -> bool | None:
        if self.error is not None:
            return False
        if self.threshold is None:
            return True
        return self.score is not None and self.score >= self.threshold

    async def a_measure(self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any) -> float:
        return self.measure(test_case, *args, **kwargs)

    @property
    def __name__(self):
        return self.name


class SuccessMetric(_DeterministicMetric):
    """Did the agent succeed: the final URL's UI state against the golden's ``expected_state``."""

    name = "Success"

    def __init__(self, app: BenchmarkApp):
        super().__init__(threshold=1.0)
        self.app = app

    def measure(self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any) -> float:
        meta = meta_of(test_case)
        self.threshold = meta.state_threshold
        if meta.expected_state is None:
            self.error = "golden has no expected_state"
            return self._finish(0.0, self.error)
        last_url = next((final_url_of(t) for t in reversed(assistant_turns(test_case)) if final_url_of(t)), None)
        match = judge_url(self.app, last_url, meta.expected_state)
        reason = f"matched {match.matched or 'nothing'}; missed {match.missed or 'nothing'}"
        if match.error:
            reason += f" ({match.error})"
        return self._finish(
            match.score, reason, {"matched": match.matched, "missed": match.missed, "final_url": last_url}
        )


class CompletionMetric(BaseConversationalMetric):
    """Did the agent complete the work: checkpoints reached (gold) averaged with deepeval's
    ConversationCompletenessMetric; the deepeval score alone on goldens without checkpoints."""

    name = "Completion"

    def __init__(self, app: BenchmarkApp, model: DeepEvalBaseLLM | str | None, threshold: float = COMPLETION_THRESHOLD):
        self.app = app
        self.threshold = threshold
        self.model = model
        self.inner = ConversationCompletenessMetric(threshold=0.0, model=model, include_reason=True)
        self.score = self.success = self.reason = self.score_breakdown = self.error = self.verbose_logs = None
        self.evaluation_cost = None

    def _checkpoints(self, test_case: ConversationalTestCase) -> tuple[float | None, list[int]]:
        meta = meta_of(test_case)
        if not meta.checkpoints:
            return None, []
        reached: list[int] = []
        for i, checkpoint in enumerate(meta.checkpoints):
            for turn in assistant_turns(test_case):
                observed = observe_or_none(self.app, final_url_of(turn))
                if observed is None:
                    continue
                if checkpoint_reached(observed, checkpoint, auto_layers=self.app.auto_layers):
                    reached.append(i)
                    break
        return len(reached) / len(meta.checkpoints), reached

    def _combine(self, test_case: ConversationalTestCase) -> float:
        fraction, reached = self._checkpoints(test_case)
        llm = self.inner.score or 0.0
        self.evaluation_cost = self.inner.evaluation_cost
        if fraction is None:
            self.score = round(llm, 4)
            self.reason = f"conversation completeness {llm:.2f}: {self.inner.reason}"
        else:
            self.score = round((fraction + llm) / 2, 4)
            self.reason = (
                f"checkpoints {fraction:.2f} (reached {reached}), conversation completeness {llm:.2f}: "
                f"{self.inner.reason}"
            )
        self.score_breakdown = {
            "checkpoints": fraction,
            "checkpoints_reached": reached,
            "conversation_completeness": llm,
        }
        self.success = self.is_successful()
        return self.score

    def measure(self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any) -> float:
        self.inner.measure(test_case, *args, **kwargs)
        return self._combine(test_case)

    async def a_measure(self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any) -> float:
        await self.inner.a_measure(test_case, *args, **kwargs)
        return self._combine(test_case)

    def is_successful(self) -> bool | None:
        if self.error is not None:
            return False
        return self.score is not None and self.score >= self.threshold

    @property
    def __name__(self):
        return self.name


def _call_key(name: str, args: dict[str, Any] | None) -> str:
    return name + ":" + json.dumps(args or {}, sort_keys=True, default=str)


class ToolEfficiencyMetric(_DeterministicMetric):
    """1 − wasted / total tool calls. Wasted: repeats of an earlier call (same tool and
    arguments), calls that errored, discovery calls on a fully specified prompt, and one
    per error turn."""

    name = "Tool efficiency"

    def __init__(self, app: BenchmarkApp, threshold: float = TOOL_EFFICIENCY_THRESHOLD):
        super().__init__(threshold=threshold)
        self.app = app

    def measure(self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any) -> float:
        meta = meta_of(test_case)
        seen: set[str] = set()
        total = 0
        wasted = {"duplicate": 0, "errored": 0, "discovery": 0, "error_turn": 0}
        per_turn: list[int] = []
        for turn in assistant_turns(test_case):
            trace = trace_of(turn)
            if (turn.metadata or {}).get("output_kind") == "error":
                wasted["error_turn"] += 1
                total += 1
            if trace is None:
                per_turn.append(0)
                continue
            per_turn.append(len(trace.tool_calls))
            for call in trace.tool_calls:
                total += 1
                key = _call_key(call.name, call.args)
                if key in seen:
                    wasted["duplicate"] += 1
                seen.add(key)
                if call.error:
                    wasted["errored"] += 1
                if meta.fully_specified and call.name in self.app.discovery_tools:
                    wasted["discovery"] += 1
        wasted_total = sum(wasted.values())
        score = 1.0 if total == 0 else max(0.0, 1 - wasted_total / total)
        reason = f"{total} tool calls, {wasted_total} wasted ({wasted})"
        return self._finish(score, reason, {"total": total, "per_turn": per_turn, "wasted": wasted})


def _turn_seconds(turn: Turn) -> float | None:
    trace = trace_of(turn)
    if trace is not None:
        return trace.duration_s
    wall = (turn.metadata or {}).get("wall_clock_s")
    return float(wall) if wall is not None else None


class TimeEfficiencyMetric(_DeterministicMetric):
    """min(1, budget / mean seconds per assistant turn)."""

    name = "Time efficiency"

    def __init__(self, threshold: float = TIME_EFFICIENCY_THRESHOLD):
        super().__init__(threshold=threshold)

    def measure(self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any) -> float:
        budgets = budgets_of(meta_of(test_case))
        seconds = [s for s in (_turn_seconds(t) for t in assistant_turns(test_case)) if s is not None]
        if budgets is None:
            self.error = "golden has no budgets"
            return self._finish(0.0, self.error)
        if not seconds:
            return self._finish(0.0, "no timed assistant turns", {"per_turn_s": []})
        mean = sum(seconds) / len(seconds)
        score = min(1.0, budgets.seconds_per_turn / mean) if mean > 0 else 1.0
        reason = f"mean {mean:.1f} s per turn against a budget of {budgets.seconds_per_turn:.0f} s"
        return self._finish(score, reason, {"per_turn_s": seconds, "total_s": sum(seconds), "mean_s": mean})


def _turn_tokens(turn: Turn) -> TurnUsage | None:
    trace = trace_of(turn)
    if trace is None:
        raw = (turn.metadata or {}).get("usage")
        return TurnUsage.model_validate(raw) if raw else None
    cache = trace.usage.cache_read_tokens if trace.usage else None
    reasoning = trace.usage.reasoning_tokens if trace.usage else None
    return TurnUsage(
        input_tokens=trace.span_input_tokens,
        output_tokens=trace.span_output_tokens,
        total_tokens=trace.span_input_tokens + trace.span_output_tokens,
        requests=len(trace.llm_calls),
        cache_read_tokens=cache,
        reasoning_tokens=reasoning,
        tool_calls=len(trace.tool_calls),
        cost_usd=trace.usage.cost_usd if trace.usage else None,
    )


class TokenEfficiencyMetric(_DeterministicMetric):
    """min(1, budget / mean cache-adjusted tokens per assistant turn)."""

    name = "Token efficiency"

    def __init__(self, threshold: float = TOKEN_EFFICIENCY_THRESHOLD):
        super().__init__(threshold=threshold)

    def measure(self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any) -> float:
        budgets = budgets_of(meta_of(test_case))
        usages = [u for u in (_turn_tokens(t) for t in assistant_turns(test_case)) if u is not None]
        if budgets is None:
            self.error = "golden has no budgets"
            return self._finish(0.0, self.error)
        adjusted = [u.cache_adjusted_tokens for u in usages if u.cache_adjusted_tokens is not None]
        if not adjusted:
            return self._finish(0.0, "no token counts on any assistant turn", {"per_turn": []})
        mean = sum(adjusted) / len(adjusted)
        score = min(1.0, budgets.tokens_per_turn / mean) if mean > 0 else 1.0
        totals = {
            "input_tokens": sum(u.input_tokens or 0 for u in usages),
            "output_tokens": sum(u.output_tokens or 0 for u in usages),
            "cache_read_tokens": sum(u.cache_read_tokens or 0 for u in usages),
            "reasoning_tokens": sum(u.reasoning_tokens or 0 for u in usages),
            "requests": sum(u.requests or 0 for u in usages),
            "cost_usd": sum(u.cost_usd or 0.0 for u in usages),
            "cache_adjusted_tokens": sum(adjusted),
            "mean_cache_adjusted_per_turn": mean,
        }
        reason = f"mean {mean:.0f} cache-adjusted tokens per turn against a budget of {budgets.tokens_per_turn}"
        return self._finish(score, reason, totals)


def turn_relevancy_metric(model: DeepEvalBaseLLM | str | None) -> TurnRelevancyMetric:
    return TurnRelevancyMetric(threshold=TURN_RELEVANCY_THRESHOLD, model=model, include_reason=True)


def gold_metrics(app: BenchmarkApp, model: DeepEvalBaseLLM | str | None) -> list[BaseConversationalMetric]:
    """All six, fresh instances (metrics hold per-test-case state)."""
    return [
        SuccessMetric(app),
        CompletionMetric(app, model),
        ToolEfficiencyMetric(app),
        TimeEfficiencyMetric(),
        TokenEfficiencyMetric(),
        turn_relevancy_metric(model),
    ]


def synthetic_metrics(app: BenchmarkApp, model: DeepEvalBaseLLM | str | None) -> list[BaseConversationalMetric]:
    """Goldens without an expected state: everything but Success."""
    return gold_metrics(app, model)[1:]


def metrics_for(
    app: BenchmarkApp, meta: GoldenMeta, model: DeepEvalBaseLLM | str | None
) -> list[BaseConversationalMetric]:
    return gold_metrics(app, model) if meta.is_gold else synthetic_metrics(app, model)


def deterministic_only(metrics: Sequence[BaseConversationalMetric]) -> list[BaseConversationalMetric]:
    return [m for m in metrics if isinstance(m, _DeterministicMetric)]


# --- simulator stopping rule ----------------------------------------------


def state_reached_controller(app: BenchmarkApp):
    """A deepeval stopping controller for gold goldens.

    Runs before every simulated user turn. Proceeds until there is an
    assistant turn; ends once the golden's extra-turn cap is used up, or
    once the last assistant URL satisfies ``expected_state`` and every
    checkpoint has been reached; otherwise proceeds (the simulated user
    asks for the next step).
    """

    def controller(
        turns: list[Turn],
        golden: Any,
        last_assistant_turn: Turn | None,
        simulated_user_turns: int,
    ) -> Decision:
        if last_assistant_turn is None:
            return proceed()
        meta = GoldenMeta.model_validate(golden.additional_metadata or {})
        if simulated_user_turns >= meta.max_user_simulations:
            return end(f"reached the golden's cap of {meta.max_user_simulations} extra user turns")
        if meta.expected_state is None:
            return proceed()
        url = final_url_of(last_assistant_turn)
        if not url:
            return proceed()
        final = judge_url(app, url, meta.expected_state)
        if final.score < 1.0:
            return proceed()
        for checkpoint in meta.checkpoints:
            hit = False
            for turn in turns:
                observed = observe_or_none(app, final_url_of(turn)) if turn.role == "assistant" else None
                if observed is None:
                    continue
                if checkpoint_reached(observed, checkpoint, auto_layers=app.auto_layers):
                    hit = True
                    break
            if not hit:
                return proceed()
        return end("expected state reached")

    return controller


__all__ = [
    "COMPLETION_THRESHOLD",
    "JUDGE_MODEL_NAME",
    "TIME_EFFICIENCY_THRESHOLD",
    "TOKEN_EFFICIENCY_THRESHOLD",
    "TOOL_EFFICIENCY_THRESHOLD",
    "TURN_RELEVANCY_THRESHOLD",
    "CompletionMetric",
    "SuccessMetric",
    "TimeEfficiencyMetric",
    "TokenEfficiencyMetric",
    "ToolEfficiencyMetric",
    "assistant_turns",
    "deterministic_only",
    "final_url_of",
    "gold_metrics",
    "judge_model",
    "meta_of",
    "metrics_for",
    "observe_or_none",
    "state_reached_controller",
    "synthetic_metrics",
    "trace_of",
    "turn_relevancy_metric",
]
