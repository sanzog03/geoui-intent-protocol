"""Reading and writing a run directory (``results/<run-id>/``)."""

from __future__ import annotations

import json
import platform
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version as _dist_version
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from geobench.harness import ConversationRecord
from geobench.records import ErrorRecord, TurnRecord, load_records, scrub_paths

CONVERSATIONS = "conversations.jsonl"
TURNS = "turns.jsonl"
ERRORS = "errors.jsonl"
RUN_INFO = "run.json"
DEEPEVAL_DIR = "deepeval"
SUMMARY_JSON = "summary.json"
SUMMARY_MD = "summary.md"


class RunInfo(BaseModel):
    """What a rerun needs to reproduce or verify this run."""

    run_name: str
    app: str = Field(description="import path 'module:Class' of the BenchmarkApp")
    reference_agent: str
    agent_kinds: list[str]
    datasets: dict[str, str] = Field(default_factory=dict, description="dataset name → sha256 of its JSON")
    judge_model: str
    agent_model: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    git_sha: str | None = None
    versions: dict[str, str] = Field(default_factory=dict)
    platform: str = Field(default_factory=platform.platform)
    extra: dict[str, Any] = Field(default_factory=dict)


def git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 — not a git checkout, or no git: the field is simply absent
        return None


def package_versions(*names: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in names:
        try:
            out[name] = _dist_version(name)
        except Exception:  # noqa: BLE001
            out[name] = "unknown"
    return out


def write_run_info(run_dir: Path, info: RunInfo) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / RUN_INFO
    path.write_text(info.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_run_info(run_dir: Path) -> RunInfo:
    return RunInfo.model_validate_json((Path(run_dir) / RUN_INFO).read_text(encoding="utf-8"))


def load_conversations(run_dir: Path) -> list[ConversationRecord]:
    return load_records(Path(run_dir) / CONVERSATIONS, ConversationRecord)


def load_turns(run_dir: Path) -> list[TurnRecord]:
    return load_records(Path(run_dir) / TURNS, TurnRecord)


def load_errors(run_dir: Path) -> list[ErrorRecord]:
    return load_records(Path(run_dir) / ERRORS, ErrorRecord)


def write_conversations(run_dir: Path, conversations: list[ConversationRecord]) -> Path:
    path = Path(run_dir) / CONVERSATIONS
    path.write_text("".join(c.model_dump_json() + "\n" for c in conversations), encoding="utf-8")
    return path


def scrub_run_dir(run_dir: Path) -> list[Path]:
    """Rewrite every text artifact so no machine-specific absolute path is committed."""
    run_dir = Path(run_dir)
    touched: list[Path] = []
    for path in sorted(run_dir.rglob("*")):
        if path.suffix not in (".jsonl", ".json", ".md") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        clean = scrub_paths(text)
        if clean != text:
            path.write_text(clean, encoding="utf-8")
            touched.append(path)
    return touched


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "CONVERSATIONS",
    "DEEPEVAL_DIR",
    "ERRORS",
    "RUN_INFO",
    "SUMMARY_JSON",
    "SUMMARY_MD",
    "TURNS",
    "RunInfo",
    "git_sha",
    "load_conversations",
    "load_errors",
    "load_json",
    "load_turns",
    "package_versions",
    "read_run_info",
    "scrub_run_dir",
    "write_conversations",
    "write_run_info",
]
