import json
from datetime import date
from pathlib import Path

import pytest
from deepeval.dataset import ConversationalGolden

from geouibench.datasets import (
    Budgets,
    DatasetError,
    GoldenMeta,
    dataset_hash,
    golden_meta,
    goldens_for,
    validate_dataset,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mini_dataset.json"
KINDS = ("a", "b")
DEFAULTS = Budgets(seconds_per_turn=60, tokens_per_turn=20000)


def test_validate_dataset_parses_metadata():
    rows = validate_dataset(FIXTURE, agent_kinds=KINDS)
    names = [g.name for g, _ in rows]
    assert names == ["single-shot", "two-step", "synthetic-like"]
    single = rows[0][1]
    assert single.is_gold and single.fully_specified and single.max_user_simulations == 0
    assert single.expected_state.time == date(2025, 9, 15)
    assert rows[1][1].checkpoints[0].layers == {"L1": None}
    assert not rows[2][1].is_gold


def test_goldens_for_injects_the_agents_opener_and_defaults():
    goldens = goldens_for(FIXTURE, "b", agent_kinds=KINDS, default_budgets=DEFAULTS)
    assert all(isinstance(g, ConversationalGolden) for g in goldens)
    first = goldens[0]
    assert [t.role for t in first.turns] == ["user"] and first.turns[0].content == "opener for b"
    assert first.additional_metadata["agent_kind"] == "b"
    assert first.additional_metadata["dataset"] == "mini_dataset"
    assert first.additional_metadata["budgets"] == {"seconds_per_turn": 60.0, "tokens_per_turn": 20000}
    assert goldens[1].additional_metadata["budgets"] == {"seconds_per_turn": 10.0, "tokens_per_turn": 1000}
    assert goldens[2].turns is None  # no openers → the simulator phrases the first turn
    assert GoldenMeta.model_validate(goldens[1].additional_metadata).expected_state.time == date(2025, 9, 16)


def test_goldens_for_rejects_unknown_kind():
    with pytest.raises(ValueError):
        goldens_for(FIXTURE, "zzz", agent_kinds=KINDS, default_budgets=DEFAULTS)


def _write(tmp_path, rows):
    p = tmp_path / "d.json"
    p.write_text(json.dumps(rows))
    return p


@pytest.mark.parametrize(
    "rows, message",
    [
        ([{"scenario": "no name"}], "needs a name"),
        ([{"name": "x", "scenario": "s"}, {"name": "x", "scenario": "t"}], "duplicate"),
        ([{"name": "x", "scenario": "s", "additional_metadata": {"openers": {"a": "only a"}}}], "openers missing"),
        ([{"name": "x", "scenario": "s", "additional_metadata": {"openers": {"a": "", "b": "y"}}}], "empty opener"),
        ([{"name": "x", "scenario": "s", "additional_metadata": {"expected_state": {"bbox": [0, 0, 1, 1]}}}], "bbox"),
        ([{"name": "x", "scenario": "s", "additional_metadata": {"checkpoints": [{}]}}], "expected_state"),
        ([{"name": "x", "scenario": "s", "turns": [{"role": "user", "content": "hi"}]}], "openers"),
    ],
)
def test_validation_errors_name_the_problem(tmp_path, rows, message):
    with pytest.raises(DatasetError, match=message):
        validate_dataset(_write(tmp_path, rows), agent_kinds=KINDS)


def test_golden_meta_defaults():
    meta = golden_meta(ConversationalGolden(scenario="s"))
    assert meta == GoldenMeta()
    assert meta.max_user_simulations == 3 and meta.state_threshold == 1.0 and not meta.is_gold


def test_dataset_hash_ignores_formatting(tmp_path):
    data = json.loads(FIXTURE.read_text())
    reformatted = tmp_path / "r.json"
    reformatted.write_text(json.dumps(data, indent=4, sort_keys=True))
    assert dataset_hash(FIXTURE) == dataset_hash(reformatted)
    data[0]["name"] = "changed"
    reformatted.write_text(json.dumps(data))
    assert dataset_hash(FIXTURE) != dataset_hash(reformatted)
