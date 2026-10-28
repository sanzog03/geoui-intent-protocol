"""Worldview bindings for geobench: the GeoUI and VLM Worldview agents under one benchmark."""

from pathlib import Path

from geobench.datasets import Budgets

#: ``benchmarks/worldview/`` — datasets, evals and results live beside this package.
BENCHMARK_DIR = Path(__file__).resolve().parent.parent
DATASETS_DIR = BENCHMARK_DIR / "datasets"
RESULTS_DIR = BENCHMARK_DIR / "results"
GOLD_DATASET = DATASETS_DIR / "gold_dataset.json"
SYNTHETIC_DATASET = DATASETS_DIR / "synthetic_queries.json"

#: Per-turn budgets the efficiency metrics score against, identical for both
#: agents and for every golden that does not override them. Chosen as "one
#: minute and twenty thousand cache-adjusted tokens per assistant turn": a
#: turn within budget scores 1.0, a turn at twice the budget scores 0.5.
#: They are a fixed yardstick, not derived from either agent's results; the
#: cross-agent comparison is the summary's ratios.
DEFAULT_BUDGETS = Budgets(seconds_per_turn=60.0, tokens_per_turn=20_000)

__all__ = ["BENCHMARK_DIR", "DATASETS_DIR", "DEFAULT_BUDGETS", "GOLD_DATASET", "RESULTS_DIR", "SYNTHETIC_DATASET"]
