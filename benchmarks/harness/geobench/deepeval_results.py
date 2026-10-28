"""Read metric scores back from deepeval after it evaluated a test case.

deepeval scores *copies* of the metric objects (``copy_metrics``), so the
instances a caller passed to ``assert_test`` stay blank. The scores live in
deepeval's test-run record; this module turns them into the plain dicts the
transcripts and the summary use.
"""

from __future__ import annotations

from typing import Any

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_run import global_test_run_manager


def metric_entry_from_data(data: Any) -> dict[str, Any]:
    """``deepeval.tracing.api.MetricData`` (or the dataclass ``TestResult`` uses) → our dict."""
    return {
        "name": data.name,
        "score": data.score,
        "success": data.success,
        "threshold": data.threshold,
        "reason": data.reason,
        "error": getattr(data, "error", None),
        "evaluation_cost": getattr(data, "evaluation_cost", None),
    }


def metric_entry(metric: BaseConversationalMetric) -> dict[str, Any]:
    """Our dict from a metric instance that was measured directly (not through deepeval)."""
    return {
        "name": metric.__name__,
        "score": metric.score,
        "success": metric.success,
        "threshold": metric.threshold,
        "reason": metric.reason,
        "breakdown": getattr(metric, "score_breakdown", None),
        "error": metric.error,
        "evaluation_cost": metric.evaluation_cost,
    }


def entries_from_current_test_run(test_case_name: str) -> list[dict[str, Any]] | None:
    """Scores deepeval recorded for ``test_case_name`` in the running ``deepeval test run``, if any."""
    try:
        test_run = global_test_run_manager.get_test_run()
    except Exception:  # noqa: BLE001 — no run in progress (plain pytest, or outside the CLI)
        return None
    if test_run is None:
        return None
    for case in reversed(test_run.conversational_test_cases or []):
        if case.name == test_case_name and case.metrics_data:
            return [metric_entry_from_data(m) for m in case.metrics_data]
    return None


__all__ = ["entries_from_current_test_run", "metric_entry", "metric_entry_from_data"]
