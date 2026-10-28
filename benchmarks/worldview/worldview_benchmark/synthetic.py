"""Build the synthetic-queries dataset with deepeval, reproducibly.

Three steps, so the generation itself stays deepeval's::

    uv run python -m worldview_benchmark.synthetic contexts <work-dir>/contexts.json
    uv run --env-file .env deepeval generate --method contexts --variation multi-turn --include-expected \\
        --contexts-file <work-dir>/contexts.json --max-goldens-per-context 2 --model gpt-5.2 \\
        --scenario-context "..." --conversational-task "..." --participant-roles "..." \\
        --scenario-format "..." --expected-outcome-format "..." \\
        --output-dir <work-dir> --file-name synthetic_queries
    uv run python -m worldview_benchmark.synthetic prepare <work-dir>/synthetic_queries.json

``contexts`` writes one context per gold golden (its scenario and expected
outcome), which is what makes the generated scenarios name real Worldview
layers. ``prepare`` adds what the harness needs and deepeval does not emit:
a stable ``name``, a persona, and ``additional_metadata`` (no openers, no
expected state: the simulator phrases every turn and only metrics 2–6 run).
The exact flags used for the committed set are in the README.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldview_benchmark import GOLD_DATASET, SYNTHETIC_DATASET

PERSONA = (
    "A domain scientist who knows what they want to see, states layers, dates and regions precisely, "
    "asks for the refinements in the scenario one at a time, and stops once the final view is shown."
)
MAX_USER_SIMULATIONS = 4


def contexts_from_gold(gold_path: Path = GOLD_DATASET) -> list[list[str]]:
    gold = json.loads(Path(gold_path).read_text(encoding="utf-8"))
    return [[f"Scenario: {g['scenario']}", f"Expected outcome: {g['expected_outcome']}"] for g in gold]


def prepare(generated: list[dict], *, method: str = "contexts") -> list[dict]:
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
                "persona": {"characteristics": PERSONA},
                "context": g.get("context"),
                "additional_metadata": {
                    "source": f"deepeval generate --method {method} (contexts built from gold_dataset.json)",
                    "fully_specified": False,
                    "max_user_simulations": MAX_USER_SIMULATIONS,
                },
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("contexts", help="write the contexts file deepeval generates from")
    c.add_argument("out", type=Path)
    c.add_argument("--gold", type=Path, default=GOLD_DATASET)
    p = sub.add_parser("prepare", help="turn deepeval's output into datasets/synthetic_queries.json")
    p.add_argument("generated", type=Path)
    p.add_argument("--out", type=Path, default=SYNTHETIC_DATASET)
    p.add_argument("--method", default="contexts")
    args = parser.parse_args(argv)

    if args.command == "contexts":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        contexts = contexts_from_gold(args.gold)
        args.out.write_text(json.dumps(contexts, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {len(contexts)} contexts to {args.out}")
        return 0

    generated = json.loads(args.generated.read_text(encoding="utf-8"))
    prepared = prepare(generated, method=args.method)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(prepared, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(prepared)} goldens to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
