"""Synthetic generation wraps deepeval's generator; the CLI runs deepeval once per agent kind."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from geouibench import cli
from geouibench.appdir import load_app_dir
from geouibench.run_dir import read_run_info
from geouibench.synthetic import SyntheticStyle, contexts_from_goldens, generate, generate_command, prepare
from geouibench.tests.test_appdir import make_app_dir

STYLE = SyntheticStyle(
    scenario_context="users of a map",
    conversational_task="show the map",
    participant_roles="user and assistant",
    scenario_format="three sentences",
    expected_outcome_format="two sentences",
    persona="precise",
    max_user_simulations=3,
    max_goldens_per_context=1,
)
GOLD = [
    {"name": "g1", "scenario": "Render A.", "expected_outcome": "A shown.", "additional_metadata": {}},
    {"name": "g2", "scenario": "Render B.", "expected_outcome": "B shown.", "additional_metadata": {}},
]
STYLED_APP_SRC = """
from geouibench.synthetic import SyntheticStyle
from geouibench.tests._fake_app import FakeApp
APP = FakeApp()
SYNTHETIC_STYLE = SyntheticStyle(
    scenario_context="c", conversational_task="t", participant_roles="r", scenario_format="s",
    expected_outcome_format="o", persona="p",
)
"""


def test_contexts_are_one_per_gold_golden(tmp_path):
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(GOLD))
    assert contexts_from_goldens(path) == [
        ["Scenario: Render A.", "Expected outcome: A shown."],
        ["Scenario: Render B.", "Expected outcome: B shown."],
    ]


def test_prepare_names_and_annotates_and_drops_empty():
    generated = [
        {"scenario": "S1", "expected_outcome": "O1", "context": ["c"]},
        {"scenario": "", "expected_outcome": "O2"},
        {"scenario": "S3", "expected_outcome": "O3"},
    ]
    out = prepare(generated, STYLE, source="src")
    assert [g["name"] for g in out] == ["synthetic-01", "synthetic-03"]
    assert out[0]["persona"] == {"characteristics": "precise"} and out[0]["context"] == ["c"]
    assert out[0]["additional_metadata"] == {"source": "src", "fully_specified": False, "max_user_simulations": 3}


def test_generate_command_carries_the_style(tmp_path):
    cmd = generate_command(STYLE, contexts_file=tmp_path / "c.json", output_dir=tmp_path, file_name="gen", model="m")
    assert cmd[0].endswith("deepeval") and cmd[1:7] == [
        "generate",
        "--method",
        "contexts",
        "--variation",
        "multi-turn",
        "--include-expected",
    ]
    assert "--scenario-context" in cmd and cmd[cmd.index("--scenario-context") + 1] == "users of a map"
    assert cmd[cmd.index("--max-goldens-per-context") + 1] == "1" and cmd[cmd.index("--model") + 1] == "m"


def test_generate_runs_deepeval_then_prepares(tmp_path):
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps(GOLD))
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        out_dir = Path(cmd[cmd.index("--output-dir") + 1])
        (out_dir / "generated.json").write_text(json.dumps([{"scenario": "S", "expected_outcome": "O"}]))

    out = tmp_path / "datasets" / "synthetic_queries.json"
    prepared = generate(STYLE, gold_path=gold, out_path=out, model="m", work_dir=tmp_path / "work", run=fake_run)
    assert (
        len(calls) == 1 and json.loads((tmp_path / "work" / "contexts.json").read_text())[0][0] == "Scenario: Render A."
    )
    assert prepared == json.loads(out.read_text()) and prepared[0]["name"] == "synthetic-01"
    assert "gold.json" in prepared[0]["additional_metadata"]["source"]


class _Spawned:
    def __init__(self, rc=0):
        self.returncode = rc


def test_run_benchmark_runs_deepeval_once_per_agent_and_summarises(tmp_path, capsys):
    app_dir = load_app_dir(make_app_dir(tmp_path, datasets={"gold_dataset": []}))
    spawned = []

    def spawn(cmd, *, env):
        spawned.append((cmd, env))
        return _Spawned(0 if env["BENCHMARK_AGENT"] == "x" else 1)

    status = cli.run_benchmark(app_dir, ["gold"], run_id="r1", smoke=True, spawn=spawn)
    assert status == 1  # one agent's deepeval run reported failures
    assert [env["BENCHMARK_AGENT"] for _, env in spawned] == ["x", "y"]
    cmd, env = spawned[0]
    assert cmd[1:3] == ["test", "run"] and cmd[3].endswith("evals/test_benchmark.py") and "--ignore-errors" in cmd
    assert env["BENCHMARK_APP"] == app_dir.relpath and env["BENCHMARK_RUN"] == "r1"
    assert env["BENCHMARK_DATASET"] == "gold" and env["BENCHMARK_SMOKE"] == "1"
    assert env["DEEPEVAL_RESULTS_FOLDER"].endswith("results/r1/deepeval") and env["DEEPEVAL_TELEMETRY_OPT_OUT"] == "YES"
    run_dir = app_dir.run_dir("r1")
    info = read_run_info(run_dir)
    assert info.run_name == "r1" and info.extra["smoke"] is True
    assert (run_dir / "summary.md").exists()
    assert "agent: x" in capsys.readouterr().out


def test_run_benchmark_applies_the_prepare_hook_env(tmp_path):
    src = """
from geouibench.tests._fake_app import FakeApp
class Prepared(FakeApp):
    def prepare(self):
        return {"PLAYWRIGHT_CDP_ENDPOINT": "http://localhost:9999"}
APP = Prepared()
"""
    app_dir = load_app_dir(make_app_dir(tmp_path, datasets={"gold_dataset": []}, src=src))
    seen = []
    cli.run_benchmark(
        app_dir, ["gold"], run_id="r2", agents=["y"], spawn=lambda cmd, *, env: seen.append(env) or _Spawned()
    )
    assert seen[0]["PLAYWRIGHT_CDP_ENDPOINT"] == "http://localhost:9999" and seen[0]["BENCHMARK_AGENT"] == "y"
    assert read_run_info(app_dir.run_dir("r2")).extra["cdp_endpoint"] == "http://localhost:9999"


def test_run_benchmark_rejects_unknown_agents_and_datasets(tmp_path):
    app_dir = load_app_dir(make_app_dir(tmp_path, datasets={"gold_dataset": []}))
    with pytest.raises(SystemExit, match="unknown agent"):
        cli.run_benchmark(app_dir, ["gold"], run_id="r", agents=["nope"], spawn=lambda *a, **k: _Spawned())
    with pytest.raises(Exception, match="no dataset named"):
        cli.run_benchmark(app_dir, ["nope"], run_id="r", spawn=lambda *a, **k: _Spawned())


def test_cli_synthetic_needs_a_style_and_datasets_lists(tmp_path, capsys, monkeypatch):
    plain = make_app_dir(tmp_path / "plain", datasets={"gold_dataset": GOLD})
    with pytest.raises(SystemExit, match="SYNTHETIC_STYLE"):
        cli.main(["synthetic", str(plain)])
    assert cli.main(["datasets", str(plain)]) == 0
    assert capsys.readouterr().out.startswith("gold_dataset\t")

    styled = make_app_dir(tmp_path / "styled", datasets={"gold_dataset": GOLD}, src=STYLED_APP_SRC)
    monkeypatch.setattr(
        "geouibench.synthetic._run_checked",
        lambda cmd: (Path(cmd[cmd.index("--output-dir") + 1]) / "generated.json").write_text(
            json.dumps([{"scenario": "S", "expected_outcome": "O"}])
        ),
    )
    assert cli.main(["synthetic", str(styled), "--work-dir", str(tmp_path / "w")]) == 0
    written = json.loads((styled / "datasets" / "synthetic_queries.json").read_text())
    assert written[0]["name"] == "synthetic-01" and written[0]["persona"] == {"characteristics": "p"}


def test_default_run_id_names_the_datasets():
    assert cli.default_run_id(["gold", "synthetic"]).endswith("-gold-synthetic")
