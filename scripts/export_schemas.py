"""Export the protocol's JSON Schemas to ``schemas/`` from the pydantic models.

pydantic is the single source of truth for the GeoUI document shape; the
committed JSON is what non-Python consumers (the ``@geoui/react`` SDK, any
other adapter) read. ``schemas/geo_intent.json`` is ``GeoIntent``'s JSON
Schema; ``schemas/extensions/<prefix>.json`` is each shipped extension's
``ExtensionSpec.describe()`` (name, uri, scope, summary, keys, required and
the fields' JSON Schema), so a consumer can advertise exactly what the
library defines. ``tests/test_schemas.py`` fails when the files drift.

Examples::

    uv run python scripts/export_schemas.py            # (re)write schemas/
    uv run python scripts/export_schemas.py --check    # exit 1 and list drifted files
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from geoui.core import GeoIntent
from geoui.extensions import ALL

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "schemas"


def generated() -> dict[Path, str]:
    """Every schema file the repo should hold, as ``{path: text}``."""
    docs: dict[Path, dict] = {SCHEMAS_DIR / "geo_intent.json": GeoIntent.model_json_schema()}
    for spec in ALL:
        docs[SCHEMAS_DIR / "extensions" / f"{spec.prefix.replace('-', '_')}.json"] = spec.describe()
    return {path: json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n" for path, doc in docs.items()}


def drifted() -> list[Path]:
    """Files whose committed text differs from the generated one (missing files count)."""
    return [p for p, text in generated().items() if not p.exists() or p.read_text() != text]


def write() -> list[Path]:
    out = []
    for path, text in generated().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        out.append(path)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report drift instead of writing")
    args = parser.parse_args(argv)
    if args.check:
        bad = drifted()
        for p in bad:
            print(f"drifted: {p.relative_to(ROOT)}")
        if bad:
            print("run: uv run python scripts/export_schemas.py")
        return 1 if bad else 0
    for p in write():
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
