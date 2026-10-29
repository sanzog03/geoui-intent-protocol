"""The committed JSON Schemas under ``schemas/`` are what the pydantic models generate (no drift)."""

import importlib.util
import json
from pathlib import Path

import pytest

from geoui.extensions import ALL

ROOT = Path(__file__).resolve().parents[1]


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_schemas", ROOT / "scripts" / "export_schemas.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = _load_exporter()


@pytest.mark.parametrize("path", sorted(exporter.generated()), ids=lambda p: str(p.relative_to(ROOT)))
def test_committed_schema_matches_generated(path):
    assert path.exists(), f"{path.relative_to(ROOT)} missing: run scripts/export_schemas.py"
    assert path.read_text() == exporter.generated()[path], (
        f"{path.relative_to(ROOT)} drifted: run scripts/export_schemas.py"
    )


def test_check_mode_is_clean():
    assert exporter.drifted() == []


def test_extension_files_name_the_library_specs():
    for spec in ALL:
        doc = json.loads((exporter.SCHEMAS_DIR / "extensions" / f"{spec.prefix.replace('-', '_')}.json").read_text())
        assert doc["name"] == spec.prefix and doc["uri"] == spec.uri and doc["scope"] == spec.scope
        assert doc == spec.describe()


def test_core_schema_is_geo_intent():
    doc = json.loads((exporter.SCHEMAS_DIR / "geo_intent.json").read_text())
    assert doc["title"] == "GeoIntent"
    assert set(doc["properties"]) >= {"geoui_version", "geoui_extensions", "viewport", "time", "layers"}
    assert doc["additionalProperties"] is True  # extension fields are namespaced extras
