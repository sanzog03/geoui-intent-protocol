"""The MapLibre gold set is the Worldview one without chart, for this app's single agent."""

import json
from pathlib import Path

from deepeval.test_case import Turn

from geouibench import load_app_dir
from geouibench.datasets import goldens_for, validate_dataset

APP_DIR = load_app_dir(Path(__file__).resolve().parent.parent)
KINDS = APP_DIR.app.agent_kinds
GOLD_DATASET = APP_DIR.dataset("gold")
EXPECTED_GOLD_NAMES = [
    "core-1-single-render",
    "core-2-date-change",
    "core-3-pan",
    "core-4-compare",
    "core-6-multilayer",
    "workflow-a-wildfire",
    "workflow-b-saharan-dust",
]


def test_gold_dataset_validates_and_is_fully_specified():
    rows = validate_dataset(GOLD_DATASET, agent_kinds=KINDS)
    assert [g.name for g, _ in rows] == EXPECTED_GOLD_NAMES
    for golden, meta in rows:
        assert meta.is_gold and meta.fully_specified, golden.name
        assert set(meta.openers) == {"geoui"}, golden.name
        assert (meta.source or "").startswith("benchmarks/worldview/datasets/gold_dataset.json#"), golden.name


def test_nothing_asks_for_chart_or_names_worldview():
    text = GOLD_DATASET.read_text()
    assert "chart" not in text.lower() and "Worldview" not in text
    for golden, meta in validate_dataset(GOLD_DATASET, agent_kinds=KINDS):
        assert meta.expected_state.chart is None, golden.name
        assert all(cp.chart is None for cp in meta.checkpoints), golden.name


def test_every_layer_id_is_in_the_demo_catalogue():
    catalogue = (APP_DIR.path.parents[1] / "demo" / "maplibre" / "src" / "layers.ts").read_text()
    for golden, meta in validate_dataset(GOLD_DATASET, agent_kinds=KINDS):
        ids = set(meta.expected_state.layers or {})
        for cp in meta.checkpoints:
            ids |= set(cp.layers or {})
        if meta.expected_state.compare and meta.expected_state.compare.layers:
            ids |= set(meta.expected_state.compare.layers)
        for layer_id in ids:
            assert f'id: "{layer_id}"' in catalogue, f"{golden.name}: {layer_id} is not in demo/maplibre/src/layers.ts"


def test_goldens_for_the_agent_have_an_opening_turn():
    goldens = goldens_for(GOLD_DATASET, "geoui", agent_kinds=KINDS, default_budgets=APP_DIR.app.budgets)
    assert len(goldens) == len(EXPECTED_GOLD_NAMES)
    for golden in goldens:
        assert golden.turns == [Turn(role="user", content=golden.additional_metadata["openers"]["geoui"])]


def test_gold_dataset_is_a_plain_json_list_for_deepeval_tools():
    data = json.loads(GOLD_DATASET.read_text())
    assert isinstance(data, list) and all("scenario" in g and "name" in g and "turns" not in g for g in data)
