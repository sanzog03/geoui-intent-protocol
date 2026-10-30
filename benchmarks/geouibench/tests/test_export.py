"""The CSV export flattens a run directory into conversation, turn and tool-call tables."""

from __future__ import annotations

import csv
from pathlib import Path

from geouibench.cli import main as cli_main
from geouibench.export import (
    CONVERSATION_FIELDS,
    CONVERSATIONS_CSV,
    CSV_DIR,
    TOOL_CALL_FIELDS,
    TOOL_CALLS_CSV,
    TURN_FIELDS,
    TURNS_CSV,
    export_run,
    export_runs,
    run_tables,
)
from geouibench.summarize import summarize_run
from geouibench.tests.test_summary_and_score import _build_run


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_run_tables_have_one_row_per_conversation_turn_and_tool_call(tmp_path):
    run_dir = _build_run(tmp_path)
    tables = run_tables(run_dir)

    assert [(r["golden"], r["agent"]) for r in tables.conversations] == [("g1", "x"), ("g1", "y")]
    x, y = tables.conversations
    assert set(x) == set(CONVERSATION_FIELDS)
    assert x["run"] == "r1" and x["dataset"] == "gold" and x["golden_kind"] == "gold"
    assert x["correctness_basis"] == "success" and x["correct"] is True and y["correct"] is False
    assert x["success_score"] == 1.0 and y["success_score"] == 0.5
    assert x["matched_fields"] == "layer:A;time" and y["missed_fields"] == "layer:A"
    assert x["expected_fields"] == 2
    assert x["assistant_turns"] == 1 and x["user_turns"] == 1 and x["error_turns"] == 0
    assert x["tool_calls"] == 1 and x["distinct_tools"] == 1 and x["wasted_tool_calls"] == 0
    assert x["tool_calls_by_name"] == '{"lookup": 1}'
    assert x["seconds"] > 0 and x["elapsed_seconds"] >= x["seconds"] and x["llm_requests"] >= 1
    assert x["first_url_turn"] == 1 and "://" in x["final_url"]
    assert x["budget_seconds_per_turn"] == 60 and x["budget_tokens_per_turn"] == 20000
    assert x["cost_complete"] in (True, False)

    assert [(r["agent"], r["turn_index"]) for r in tables.turns] == [("x", 1), ("y", 1)]
    turn = tables.turns[0]
    assert set(turn) == set(TURN_FIELDS)
    assert turn["tool_names"] == "lookup" and turn["has_url"] is True and turn["output_kind"] == "structured"
    assert turn["trace_duration_s"] != "" and turn["llm_seconds"] != ""

    assert [(r["agent"], r["tool"], r["call_index"]) for r in tables.tool_calls] == [
        ("x", "lookup", 1),
        ("y", "lookup", 1),
    ]
    call = tables.tool_calls[0]
    assert set(call) == set(TOOL_CALL_FIELDS)
    assert call["is_duplicate"] is False and call["is_discovery"] is False and call["args_chars"] > 0


def test_export_run_writes_the_three_csvs_and_summarize_refreshes_them(tmp_path):
    run_dir = _build_run(tmp_path)
    paths = export_run(run_dir)
    assert set(paths) == {"conversations", "turns", "tool_calls"}
    out = run_dir / CSV_DIR
    assert {p.name for p in out.iterdir()} == {CONVERSATIONS_CSV, TURNS_CSV, TOOL_CALLS_CSV}
    rows = _read(out / CONVERSATIONS_CSV)
    assert list(rows[0]) == CONVERSATION_FIELDS
    assert [(r["golden"], r["agent"], r["correct"]) for r in rows] == [("g1", "x", "True"), ("g1", "y", "False")]
    assert rows[0]["success_pass"] == "True" and rows[1]["success_pass"] == "False"
    assert rows[0]["completion_score"] == ""  # not scored in this offline run: blank, not zero

    (out / CONVERSATIONS_CSV).unlink()
    summarize_run(run_dir)
    assert (out / CONVERSATIONS_CSV).exists()


def test_export_runs_concatenates_and_names_the_run(tmp_path):
    a = _build_run(tmp_path / "a")
    b = _build_run(tmp_path / "b")
    out = tmp_path / "combined"
    export_runs([a, b], out)
    rows = _read(out / CONVERSATIONS_CSV)
    assert len(rows) == 4 and {r["run"] for r in rows} == {"r1"}
    assert len(_read(out / TURNS_CSV)) == 4 and len(_read(out / TOOL_CALLS_CSV)) == 4


def test_cli_export(tmp_path, capsys):
    run_dir = _build_run(tmp_path)
    assert cli_main(["export", str(run_dir)]) == 0
    assert (run_dir / CSV_DIR / TURNS_CSV).exists()
    assert str(run_dir / CSV_DIR) in capsys.readouterr().out
    assert cli_main(["export", str(run_dir), "--out", str(tmp_path / "x")]) == 0
    assert (tmp_path / "x" / TOOL_CALLS_CSV).exists()
