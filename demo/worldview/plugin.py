"""Load a Claude Code plugin / skill for use with a bare pydantic-ai ``Agent``.

A Claude Code plugin is a directory with ``.claude-plugin/plugin.json``
(metadata and ``userConfig`` declarations), ``.mcp.json`` (MCP servers whose
secrets are written as ``${user_config.<key>}`` placeholders) and one or more
skills under ``skills/<name>/`` (``SKILL.md`` entry point plus a
``references/`` tree the skill tells the model to consult on demand).

This module turns those three things into pydantic-ai building blocks:

- :func:`load_skill` → the ``SKILL.md`` body, used as the system prompt.
- :func:`reference_toolset` → ``list_references`` / ``read_reference`` tools
  so the model can open the detailed documents the skill points at, the way
  Claude Code discloses a skill progressively.
- :func:`load_mcp_config` → pydantic-ai MCP servers from ``.mcp.json`` with
  the ``${user_config.*}`` placeholders filled from the environment; servers
  whose secret is missing are dropped with a warning instead of being sent a
  ``Bearer None`` header.
- :func:`remote_capabilities` / :func:`playwright_server` → the capability
  objects the agents consume.

Nothing here touches the network at import time or at load time; servers
connect only when an agent run starts.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import ModelRetry
from pydantic_ai.capabilities import MCP
from pydantic_ai.mcp import MCPServerConfig, MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP
from pydantic_ai.toolsets import FunctionToolset

log = logging.getLogger(__name__)

MCPServer = MCPServerStdio | MCPServerStreamableHTTP | MCPServerSSE

_DEMO_DIR = Path(__file__).resolve().parents[1]

#: The ``worldview-assistant`` plugin, vendored as a git submodule of
#: NASA-IMPACT/akd-plugins. Override with ``WORLDVIEW_PLUGIN_DIR``.
DEFAULT_PLUGIN_DIR = _DEMO_DIR / "vendor" / "akd-plugins" / "plugins" / "worldview-assistant"

#: The non-GeoUI skill the baseline agent runs (vendored copy, see its README).
MIO_SKILL_DIR = _DEMO_DIR / "skills" / "mio-worldviewagent-v2"

#: Remote MCP servers get this long to initialise. The 5 s pydantic-ai default
#: trips on FastMCP Cloud cold starts (anyio.fail_after inside mcp.py).
REMOTE_MCP_INIT_TIMEOUT_S = 30.0

#: Servers the demo serves in-process (``worldview.tools.pai``) or configures
#: itself (Playwright over CDP) rather than taking from the plugin config.
LOCAL_SERVER_NAMES: tuple[str, ...] = ("geoui", "worldview-permalink", "playwright")

#: ``userConfig`` keys that do not follow the ``KEY.upper()`` convention.
USER_CONFIG_ENV_ALIASES: Mapping[str, str] = {"vector_db_token": "VECTOR_DB_TOOL_KEY"}

_USER_CONFIG_RE = re.compile(r"\$\{user_config\.([A-Za-z0-9_]+)\}")
_FRONTMATTER_RE = re.compile(r"\A\s*---\n.*?\n---\n", re.DOTALL)


# -----------------------------------------------------------------------------
# Plugin directory
# -----------------------------------------------------------------------------


def plugin_dir() -> Path:
    """Resolve the plugin directory, honouring ``WORLDVIEW_PLUGIN_DIR``."""
    override = os.environ.get("WORLDVIEW_PLUGIN_DIR")
    path = Path(override).expanduser() if override else DEFAULT_PLUGIN_DIR
    if not (path / ".mcp.json").is_file():
        hint = (
            "set WORLDVIEW_PLUGIN_DIR to a checkout of the worldview-assistant plugin"
            if override
            else "run `git submodule update --init` from the repo root, or set WORLDVIEW_PLUGIN_DIR"
        )
        raise FileNotFoundError(f"No Claude plugin at {path} (missing .mcp.json); {hint}.")
    return path


# -----------------------------------------------------------------------------
# Skills
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Skill:
    """A loaded Claude skill: the ``SKILL.md`` body plus where its references live."""

    name: str
    description: str
    body: str
    path: Path

    @property
    def references_dir(self) -> Path:
        return self.path / "references"


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Strip every leading ``---`` block (some exports carry two) and return the
    scalar keys of the first one plus the remaining markdown body."""
    meta: dict[str, str] = {}
    first = True
    while (m := _FRONTMATTER_RE.match(text)) is not None:
        if first:
            for line in m.group(0).splitlines()[1:-1]:
                key, sep, value = line.partition(":")
                if sep and not line.startswith((" ", "\t")):
                    meta[key.strip()] = value.strip().strip("'\"")
            first = False
        text = text[m.end() :]
    return meta, text.strip() + "\n"


def load_skill(skill_dir: Path) -> Skill:
    """Read ``<skill_dir>/SKILL.md``; the returned ``body`` is the system prompt."""
    skill_dir = Path(skill_dir)
    meta, body = _split_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    return Skill(
        name=meta.get("name", skill_dir.name),
        description=meta.get("description", ""),
        body=body,
        path=skill_dir,
    )


def _reference_paths(skill: Skill) -> list[str]:
    root = skill.references_dir
    if not root.is_dir():
        return []
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def reference_toolset(skill: Skill) -> FunctionToolset:
    """Two tools that let the model open the skill's ``references/`` documents on
    demand: the "Available context (documents)" the skill text refers to."""
    toolset = FunctionToolset(id=f"{skill.name}-references")
    root = skill.references_dir.resolve()

    @toolset.tool_plain(
        name="list_references",
        description=(
            "List the reference documents that ship with this skill (relative paths under "
            "references/: contexts/, guardrails/, tools/<tool>/index.md, output.md, "
            "reasoning.md, scope.md). Call read_reference to open one."
        ),
    )
    def list_references() -> list[str]:
        return _reference_paths(skill)

    @toolset.tool_plain(
        name="read_reference",
        description=(
            "Read one of this skill's reference documents by its relative path as returned by "
            "list_references (for example 'tools/geo_ui_render_intent_tool/index.md' or "
            "'output.md'). Use it when the skill text says to consult a document."
        ),
    )
    def read_reference(path: str) -> str:
        target = (root / path).resolve()
        if root not in target.parents and target != root:
            raise ModelRetry(f"'{path}' is outside the skill's references/ directory.")
        if not target.is_file():
            raise ModelRetry(f"No reference document at '{path}'. Call list_references for the available paths.")
        return target.read_text(encoding="utf-8")

    return toolset


# -----------------------------------------------------------------------------
# MCP servers from .mcp.json
# -----------------------------------------------------------------------------


def user_config_keys(plugin_root: Path) -> list[str]:
    """The ``userConfig`` keys declared in ``.claude-plugin/plugin.json``."""
    manifest = plugin_root / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        return []
    return list(json.loads(manifest.read_text(encoding="utf-8")).get("userConfig", {}))


def env_var_for(key: str) -> str:
    """Environment variable that supplies ``${user_config.<key>}``."""
    return USER_CONFIG_ENV_ALIASES.get(key, key.upper())


def user_config_from_env(plugin_root: Path, environ: Mapping[str, str] | None = None) -> dict[str, str | None]:
    """Values for every declared ``userConfig`` key, ``None`` when unset or empty."""
    environ = os.environ if environ is None else environ
    return {key: (environ.get(env_var_for(key)) or None) for key in user_config_keys(plugin_root)}


def _substitute(value: object, user_config: Mapping[str, str | None], missing: set[str]) -> object:
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            resolved = user_config.get(key)
            if resolved is None:
                missing.add(key)
                return ""
            return resolved

        return _USER_CONFIG_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute(v, user_config, missing) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, user_config, missing) for v in value]
    return value


def load_mcp_config(
    plugin_root: Path,
    *,
    user_config: Mapping[str, str | None],
    timeout: float = REMOTE_MCP_INIT_TIMEOUT_S,
) -> dict[str, MCPServer]:
    """Build pydantic-ai MCP servers from the plugin's ``.mcp.json``.

    ``${user_config.<key>}`` placeholders are filled from ``user_config``. A
    server that still needs a key you have not provided is left out and logged,
    so the agent runs with fewer tools rather than failing every call with a
    401. Server ``id`` is the config name; no ``tool_prefix`` is applied because
    the skill text names the tools bare.
    """
    raw = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
    entries: dict[str, dict] = {}
    for name, entry in raw.get("mcpServers", {}).items():
        missing: set[str] = set()
        substituted = _substitute(entry, user_config, missing)
        if missing:
            needed = ", ".join(env_var_for(k) for k in sorted(missing))
            log.warning("MCP server %r skipped: set %s to enable it", name, needed)
            continue
        assert isinstance(substituted, dict)
        entries[name] = {k: v for k, v in substituted.items() if k != "type"}  # pydantic-ai infers the transport
    config = MCPServerConfig.model_validate({"mcpServers": entries})
    servers: dict[str, MCPServer] = {}
    for name, server in config.mcp_servers.items():
        server.id = name
        server.timeout = timeout
        servers[name] = server
    return servers


def remote_capabilities(
    servers: Mapping[str, MCPServer],
    *,
    exclude: Iterable[str] = LOCAL_SERVER_NAMES,
) -> list[MCP]:
    """One ``MCP`` capability per remote server, skipping the ones the demo
    provides itself. ``builtin=False`` forces pydantic-ai's local client, which
    respects the CMR URL's load-bearing trailing slash."""
    skip = set(exclude)
    caps: list[MCP] = []
    for name, server in servers.items():
        if name in skip or not isinstance(server, MCPServerStreamableHTTP | MCPServerSSE):
            continue
        caps.append(MCP(url=server.url, local=server, builtin=False, id=name))
    return caps


def playwright_server(
    servers: Mapping[str, MCPServer],
    cdp_endpoint: str | None,
    *,
    timeout: float = REMOTE_MCP_INIT_TIMEOUT_S,
) -> MCPServerStdio:
    """The plugin's Playwright MCP, attached to an already-running Chromium when
    ``cdp_endpoint`` is given (see the CDP design note in ``agents._common``).
    A fresh instance is returned every call; one Playwright MCP must not be
    shared across agent runs."""
    base = servers.get("playwright")
    if not isinstance(base, MCPServerStdio):
        raise KeyError("plugin .mcp.json has no stdio 'playwright' server")
    args = list(base.args)
    if cdp_endpoint:
        args += ["--cdp-endpoint", cdp_endpoint]
    return MCPServerStdio(base.command, args, env=base.env, id="playwright", timeout=timeout)


__all__ = [
    "DEFAULT_PLUGIN_DIR",
    "LOCAL_SERVER_NAMES",
    "MIO_SKILL_DIR",
    "REMOTE_MCP_INIT_TIMEOUT_S",
    "USER_CONFIG_ENV_ALIASES",
    "MCPServer",
    "Skill",
    "env_var_for",
    "load_mcp_config",
    "load_skill",
    "playwright_server",
    "plugin_dir",
    "reference_toolset",
    "remote_capabilities",
    "user_config_from_env",
    "user_config_keys",
]
