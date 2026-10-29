"""Conversational goldens with the benchmark's own metadata.

A dataset file is a plain JSON list of deepeval ``ConversationalGolden``
objects, so deepeval's loaders and ``deepeval generate --method goldens``
read it unchanged. Everything the harness adds rides in
``additional_metadata`` and is validated here as :class:`GoldenMeta`:

- ``openers``: the verbatim first user turn per agent kind (gold set only);
  :func:`goldens_for` turns it into the golden's opening ``Turn`` so the
  simulator answers it before improvising the rest;
- ``expected_state`` / ``checkpoints``: what the state judge checks
  (absent on synthetic goldens, which are judged by the LLM metrics only);
- ``max_user_simulations``: how many *extra* user turns the simulator may
  add after the opener (0 = single-shot);
- ``state_threshold``, ``fully_specified``, ``budgets``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from deepeval.dataset import ConversationalGolden, EvaluationDataset
from deepeval.test_case import Turn
from pydantic import BaseModel, ConfigDict, Field, model_validator

from geouibench.state import ExpectedState


class Budgets(BaseModel):
    """Per-turn budgets the efficiency metrics score against; identical for every agent kind."""

    model_config = ConfigDict(extra="forbid")

    seconds_per_turn: float = Field(gt=0)
    tokens_per_turn: int = Field(gt=0, description="Cache-adjusted tokens per assistant turn")


class GoldenMeta(BaseModel):
    """The harness's slice of a golden's ``additional_metadata``."""

    model_config = ConfigDict(extra="allow")

    source: str | None = None
    fully_specified: bool = False
    openers: dict[str, str] | None = None
    max_user_simulations: int = Field(default=3, ge=0)
    state_threshold: float = Field(default=1.0, ge=0.0, le=1.0)
    expected_state: ExpectedState | None = None
    checkpoints: list[ExpectedState] = Field(default_factory=list)
    budgets: Budgets | None = None

    @property
    def is_gold(self) -> bool:
        return self.expected_state is not None

    @model_validator(mode="after")
    def _single_shot_has_no_checkpoints_beyond_final(self) -> GoldenMeta:
        if self.expected_state is None and self.checkpoints:
            raise ValueError("checkpoints need an expected_state")
        return self


class DatasetError(ValueError):
    """A dataset file failed validation; the message names the golden and the problem."""


def load_goldens(path: Path) -> list[ConversationalGolden]:
    """Load a dataset file through deepeval's own loader (a JSON list of conversational goldens)."""
    dataset = EvaluationDataset()
    dataset.add_goldens_from_json_file(file_path=str(path))
    goldens = [g for g in dataset.goldens if isinstance(g, ConversationalGolden)]
    if len(goldens) != len(dataset.goldens):
        raise DatasetError(f"{path}: every entry must be a conversational golden (has 'scenario')")
    return goldens


def golden_meta(golden: ConversationalGolden) -> GoldenMeta:
    try:
        return GoldenMeta.model_validate(golden.additional_metadata or {})
    except ValueError as exc:
        raise DatasetError(f"golden {golden.name!r}: {exc}") from exc


def validate_dataset(path: Path, *, agent_kinds: tuple[str, ...]) -> list[tuple[ConversationalGolden, GoldenMeta]]:
    """Load and validate; returns each golden with its parsed metadata."""
    goldens = load_goldens(path)
    seen: set[str] = set()
    out: list[tuple[ConversationalGolden, GoldenMeta]] = []
    for golden in goldens:
        if not golden.name:
            raise DatasetError(f"{path}: every golden needs a name (scenario starts {golden.scenario[:40]!r})")
        if golden.name in seen:
            raise DatasetError(f"{path}: duplicate golden name {golden.name!r}")
        seen.add(golden.name)
        if not golden.scenario.strip():
            raise DatasetError(f"golden {golden.name!r}: empty scenario")
        meta = golden_meta(golden)
        if meta.openers is not None:
            missing = set(agent_kinds) - set(meta.openers)
            if missing:
                raise DatasetError(f"golden {golden.name!r}: openers missing for {sorted(missing)}")
            for kind, text in meta.openers.items():
                if not text.strip():
                    raise DatasetError(f"golden {golden.name!r}: empty opener for {kind!r}")
        if golden.turns:
            raise DatasetError(f"golden {golden.name!r}: store openers in additional_metadata.openers, not turns")
        out.append((golden, meta))
    return out


def goldens_for(
    path: Path,
    agent_kind: str,
    *,
    agent_kinds: tuple[str, ...],
    default_budgets: Budgets,
) -> list[ConversationalGolden]:
    """The dataset's goldens prepared for one agent kind.

    Each returned golden carries the verbatim opener as its first user
    ``Turn`` (when the dataset has openers), and its ``additional_metadata``
    is normalised (budgets filled from ``default_budgets``) and extended
    with ``agent_kind`` and ``dataset``.
    """
    if agent_kind not in agent_kinds:
        raise ValueError(f"unknown agent kind {agent_kind!r}; expected one of {agent_kinds}")
    prepared: list[ConversationalGolden] = []
    for golden, meta in validate_dataset(path, agent_kinds=agent_kinds):
        if meta.budgets is None:
            meta = meta.model_copy(update={"budgets": default_budgets})
        metadata = {
            **(golden.additional_metadata or {}),
            **meta.model_dump(mode="json", exclude_none=True),
            "agent_kind": agent_kind,
            "dataset": path.stem,
        }
        turns = [Turn(role="user", content=meta.openers[agent_kind])] if meta.openers else None
        prepared.append(
            golden.model_copy(update={"turns": turns, "additional_metadata": metadata}),
        )
    return prepared


def dataset_hash(path: Path) -> str:
    """sha256 of the canonical JSON, recorded in run.json so a rerun can prove it used the same goldens."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "Budgets",
    "DatasetError",
    "GoldenMeta",
    "dataset_hash",
    "golden_meta",
    "goldens_for",
    "load_goldens",
    "validate_dataset",
]
