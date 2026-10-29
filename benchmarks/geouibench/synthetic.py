"""Generate a synthetic dataset from a gold one with deepeval, reproducibly.

Three steps, so the generation itself stays deepeval's:

1. :func:`contexts_from_goldens` turns every gold golden (its scenario and
   expected outcome) into one context, which is what makes the generated
   scenarios name the application's real layers and operations;
2. ``deepeval generate --method contexts --variation multi-turn`` runs with
   the app's :class:`SyntheticStyle` (what the user is like, what the
   assistant does, how a scenario and an outcome should read);
3. :func:`prepare` adds what the utility needs and deepeval does not emit:
   a stable ``name``, the persona, and ``additional_metadata`` (no openers,
   no expected state: the simulator phrases every turn and only the metrics
   that need no expected state run).

:func:`generate` does all three; ``geouibench synthetic <app dir>`` is its CLI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class SyntheticStyle(BaseModel):
    """The application-specific wording handed to ``deepeval generate``."""

    model_config = ConfigDict(extra="forbid")

    scenario_context: str = Field(description="Who the users are and what they ask the assistant for")
    conversational_task: str = Field(description="What the assistant must do in every conversation")
    participant_roles: str = Field(description="e.g. 'A domain scientist (user) and the assistant'")
    scenario_format: str = Field(description="How a generated scenario should read")
    expected_outcome_format: str = Field(description="How a generated expected outcome should read")
    persona: str = Field(description="The simulated user's persona on every generated golden")
    max_user_simulations: int = Field(default=4, ge=1, description="Extra user turns the simulator may add")
    max_goldens_per_context: int = Field(default=2, ge=1)


def contexts_from_goldens(gold_path: Path) -> list[list[str]]:
    gold = json.loads(Path(gold_path).read_text(encoding="utf-8"))
    return [[f"Scenario: {g['scenario']}", f"Expected outcome: {g['expected_outcome']}"] for g in gold]


def prepare(generated: list[dict], style: SyntheticStyle, *, source: str) -> list[dict]:
    out: list[dict] = []
    for i, g in enumerate(generated, 1):
        scenario = (g.get("scenario") or "").strip()
        outcome = (g.get("expected_outcome") or "").strip()
        if not scenario or not outcome:
            continue
        out.append(
            {
                "name": f"synthetic-{i:02d}",
                "scenario": scenario,
                "expected_outcome": outcome,
                "persona": {"characteristics": style.persona},
                "context": g.get("context"),
                "additional_metadata": {
                    "source": source,
                    "fully_specified": False,
                    "max_user_simulations": style.max_user_simulations,
                },
            }
        )
    return out


def deepeval_executable() -> str:
    """The ``deepeval`` CLI next to the running interpreter (the same environment), or on PATH."""
    beside = Path(sys.executable).parent / "deepeval"
    if beside.is_file():
        return str(beside)
    found = shutil.which("deepeval")
    if found is None:
        raise FileNotFoundError("the deepeval CLI is not installed in this environment")
    return found


def generate_command(
    style: SyntheticStyle, *, contexts_file: Path, output_dir: Path, file_name: str, model: str
) -> list[str]:
    return [
        deepeval_executable(),
        "generate",
        "--method",
        "contexts",
        "--variation",
        "multi-turn",
        "--include-expected",
        "--contexts-file",
        str(contexts_file),
        "--max-goldens-per-context",
        str(style.max_goldens_per_context),
        "--model",
        model,
        "--scenario-context",
        style.scenario_context,
        "--conversational-task",
        style.conversational_task,
        "--participant-roles",
        style.participant_roles,
        "--scenario-format",
        style.scenario_format,
        "--expected-outcome-format",
        style.expected_outcome_format,
        "--output-dir",
        str(output_dir),
        "--file-name",
        file_name,
    ]


def generate(
    style: SyntheticStyle,
    *,
    gold_path: Path,
    out_path: Path,
    model: str,
    work_dir: Path | None = None,
    run: callable[[list[str]], None] | None = None,
) -> list[dict]:
    """Gold → contexts → ``deepeval generate`` → prepared synthetic dataset written to ``out_path``."""
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="geouibench-synthetic-"))
    work.mkdir(parents=True, exist_ok=True)
    contexts_file = work / "contexts.json"
    contexts_file.write_text(json.dumps(contexts_from_goldens(gold_path), indent=1, ensure_ascii=False), "utf-8")
    cmd = generate_command(style, contexts_file=contexts_file, output_dir=work, file_name="generated", model=model)
    (run or _run_checked)(cmd)
    generated = json.loads((work / "generated.json").read_text(encoding="utf-8"))
    prepared = prepare(
        generated, style, source=f"deepeval generate --method contexts (contexts built from {Path(gold_path).name})"
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(prepared, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return prepared


def _run_checked(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


__all__ = [
    "SyntheticStyle",
    "contexts_from_goldens",
    "deepeval_executable",
    "generate",
    "generate_command",
    "prepare",
]
