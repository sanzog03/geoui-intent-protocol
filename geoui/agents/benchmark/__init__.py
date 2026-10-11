"""Lightweight per-turn logging for the GeoUI vs VLM-baseline comparison.

Both demo chat notebooks (``demo/geoui_chat.py``, ``demo/vlm_chat.py``)
call :func:`append_turn_record` after each completed (or errored)
agent turn; records are appended as JSON Lines to
``benchmarks/runs.jsonl`` under the current working directory (the repo
root when launched via ``demo/start.sh``). A separate analysis
script (or notebook cell) can then read the file and produce
poster-ready summaries — see :func:`load_runs`.
"""

from geoui.agents.benchmark.log import (
    DEFAULT_ERROR_LOG_PATH,
    DEFAULT_LOG_PATH,
    ErrorRecord,
    TurnRecord,
    TurnUsage,
    append_error_record,
    append_turn_record,
    extract_usage,
    load_runs,
    new_session_id,
)

__all__ = [
    "DEFAULT_ERROR_LOG_PATH",
    "DEFAULT_LOG_PATH",
    "ErrorRecord",
    "TurnRecord",
    "TurnUsage",
    "append_error_record",
    "append_turn_record",
    "extract_usage",
    "load_runs",
    "new_session_id",
]
