"""Serialize every model-visible / logged surface of an IESO Worldview agent.

Used by ``demo/worldview/tests/agents/test_agent_surface.py`` (assert against the golden) and
``scripts/capture_agent_surface.py`` (regenerate the golden). Anything that
reaches the model prompt, the pydantic-ai tool definitions, or the benchmark
log rows is included; internals that do not (e.g. input schema class names)
are left out on purpose.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

_CAP_FIELDS = ("id", "url", "allowed_tools", "description", "builtin", "effort")


def _capability(cap: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"type": type(cap).__name__}
    for name in _CAP_FIELDS:
        entry[name] = getattr(cap, name, None)
    local = getattr(cap, "local", None)
    if local is not None:
        entry["local"] = {
            "type": type(local).__name__,
            "command": getattr(local, "command", None),
            "args": getattr(local, "args", None),
            "timeout": getattr(local, "timeout", None),
            "url": getattr(local, "url", None),
        }
    return entry


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    return {
        "name": model.__name__,
        "doc": model.__doc__,
        "fields": {name: field.description for name, field in model.model_fields.items()},
        "response_field": getattr(model, "__response_field__", None),
    }


def surface(agent_cls: type, *, make_playwright_mcp: Any, playwright_capability: Any) -> dict[str, Any]:
    """Build the surface dict for ``agent_cls`` under dummy credentials."""
    os.environ.setdefault("OPENAI_API_KEY", "dummy")
    os.environ.setdefault("VECTOR_DB_TOOL_KEY", "dummy")

    agent = agent_cls()
    config = agent.config
    outputs = getattr(agent.output_schema, "__args__", (agent.output_schema,))
    playwright = playwright_capability(make_playwright_mcp("http://localhost:9222"))

    return {
        "agent_class": agent_cls.__name__,
        "agent_name": agent.name,
        "config_class": type(config).__name__,
        "description": config.description,
        "system_prompt": config.system_prompt,
        "model_name": config.model_name,
        "reasoning_effort": config.reasoning_effort,
        "tools": [t.name for t in config.tools],
        "tool_descriptions": {t.name: t.description for t in config.tools},
        "capabilities": [_capability(c) for c in config.capabilities],
        "playwright_capability": _capability(playwright),
        "input_schema": {"fields": _schema(agent.input_schema)["fields"]},
        "output_schemas": [_schema(m) for m in outputs],
    }
