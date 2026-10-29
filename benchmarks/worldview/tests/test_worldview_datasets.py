"""The committed datasets validate and carry what the runs need."""

import json
from pathlib import Path

import pytest
from deepeval.test_case import Turn

from geouibench import load_app_dir
from geouibench.datasets import goldens_for, validate_dataset

APP_DIR = load_app_dir(Path(__file__).resolve().parent.parent)
KINDS = APP_DIR.app.agent_kinds
DEFAULT_BUDGETS = APP_DIR.app.budgets
GOLD_DATASET = APP_DIR.dataset("gold")
SYNTHETIC_DATASET = APP_DIR.datasets_dir / "synthetic_queries.json"
EXPECTED_GOLD_NAMES = [
    "core-1-single-render",
    "core-2-date-change",
    "core-3-pan",
    "core-4-compare",
    "core-5-chart",
    "core-6-multilayer",
    "workflow-a-wildfire",
    "workflow-b-saharan-dust",
]


def test_gold_dataset_validates_and_is_fully_specified():
    rows = validate_dataset(GOLD_DATASET, agent_kinds=KINDS)
    assert [g.name for g, _ in rows] == EXPECTED_GOLD_NAMES
    for golden, meta in rows:
        assert meta.is_gold, golden.name
        assert meta.fully_specified, golden.name
        assert meta.openers and set(meta.openers) == set(KINDS), golden.name
        assert golden.expected_outcome and golden.persona and golden.persona.characteristics, golden.name
        assert (meta.source or "").startswith("benchmarks/manual/"), golden.name


def test_gold_openers_follow_the_prompts_md_convention():
    for golden, meta in validate_dataset(GOLD_DATASET, agent_kinds=KINDS):
        geoui, vlm = meta.openers["geoui"], meta.openers["vlm"]
        assert "`" in geoui and "exact layer ID" in geoui, golden.name
        assert '"' in vlm and "Worldview's" in vlm and "`" not in vlm, golden.name


def test_gold_goldens_for_each_agent_have_an_opening_turn():
    for kind in KINDS:
        goldens = goldens_for(GOLD_DATASET, kind, agent_kinds=KINDS, default_budgets=DEFAULT_BUDGETS)
        assert len(goldens) == len(EXPECTED_GOLD_NAMES)
        for golden in goldens:
            assert golden.turns == [Turn(role="user", content=golden.additional_metadata["openers"][kind])]
            assert golden.additional_metadata["budgets"] == DEFAULT_BUDGETS.model_dump()
            assert golden.additional_metadata["agent_kind"] == kind


def test_workflows_have_checkpoints_and_a_relaxed_threshold():
    by_name = {g.name: m for g, m in validate_dataset(GOLD_DATASET, agent_kinds=KINDS)}
    for name in ("workflow-a-wildfire", "workflow-b-saharan-dust"):
        meta = by_name[name]
        assert meta.max_user_simulations == 4 and meta.state_threshold == 0.8 and len(meta.checkpoints) >= 4
    for name in ("core-1-single-render", "core-4-compare", "core-5-chart", "core-6-multilayer"):
        assert by_name[name].max_user_simulations == 0 and by_name[name].state_threshold == 1.0


def test_gold_dataset_is_a_plain_json_list_for_deepeval_tools():
    data = json.loads(GOLD_DATASET.read_text())
    assert isinstance(data, list) and all("scenario" in g and "name" in g for g in data)
    assert all("turns" not in g for g in data)


@pytest.mark.skipif(not SYNTHETIC_DATASET.exists(), reason="synthetic queries not generated yet")
def test_synthetic_dataset_validates_without_expected_state():
    for golden, meta in validate_dataset(SYNTHETIC_DATASET, agent_kinds=KINDS):
        assert not meta.is_gold, golden.name
        assert golden.expected_outcome, golden.name
