"""Serialize every model-visible / logged surface of a Worldview agent.

Used by ``demo/worldview/tests/agents/test_agent_surface.py`` (assert against
the golden) and ``scripts/capture_agent_surface.py`` (regenerate the golden).
Anything that reaches the model (system prompts, tool names, descriptions and
parameter schemas, output tool names, capability ids and allow-lists) or the
benchmark log rows is included. No network: MCP servers are constructed but
never connected, and every plugin secret is a dummy value so all servers are
present.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel
from pydantic_ai.toolsets import FunctionToolset

from worldview.agents._common import AgentSpec, TextOutput, build_agent
from worldview.plugin import DEFAULT_PLUGIN_DIR, env_var_for, user_config_keys

DUMMY_ENV: dict[str, str] = {
    "OPENAI_API_KEY": "dummy",
    **{env_var_for(key): f"dummy-{key}" for key in user_config_keys(DEFAULT_PLUGIN_DIR)},
}
CDP_ENDPOINT = "http://localhost:9222"

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
            "args": list(getattr(local, "args", None) or []) or None,
            "timeout": getattr(local, "timeout", None),
            "url": getattr(local, "url", None),
            "header_names": sorted((getattr(local, "headers", None) or {}).keys()) or None,
        }
    return entry


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    return {
        "name": model.__name__,
        "doc": model.__doc__,
        "fields": {name: field.description for name, field in model.model_fields.items()},
    }


def _local_tools(spec: AgentSpec) -> dict[str, dict[str, Any]]:
    tools: dict[str, dict[str, Any]] = {}
    for toolset in spec.toolsets:
        if isinstance(toolset, FunctionToolset):
            for name, tool in toolset.tools.items():
                tools[name] = {
                    "toolset": toolset.id,
                    "description": tool.description,
                    "parameters": tool.function_schema.json_schema,
                }
    return tools


def surface(spec: AgentSpec) -> dict[str, Any]:
    """Build the surface dict for an :class:`AgentSpec` (built with ``DUMMY_ENV``)."""
    os.environ.setdefault("OPENAI_API_KEY", "dummy")  # the OpenAI provider refuses to instantiate without one
    agent = build_agent(spec)
    output_toolset = agent._output_schema.toolset  # pydantic-ai internal; the output tool defs the model sees
    output_tools = [
        {"name": td.name, "description": td.description} for td in getattr(output_toolset, "_tool_defs", [])
    ]
    return {
        "agent_name": agent.name,
        "model_name": agent.model.model_name if agent.model is not None else None,
        "system_prompts": list(agent._system_prompts),
        "local_tools": _local_tools(spec),
        "capabilities": [_capability(c) for c in spec.capabilities],
        "servers": sorted(spec.servers),
        "output_tools": output_tools,
        "output_schemas": [_schema(spec.output_cls), _schema(TextOutput)],
        "retries": spec.retries,
    }
