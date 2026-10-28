"""Tests for the Claude plugin / skill loader (``worldview.plugin``). No network."""

import json
from pathlib import Path

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.mcp import MCPServerStdio, MCPServerStreamableHTTP

from worldview import plugin
from worldview.plugin import (
    DEFAULT_PLUGIN_DIR,
    MIO_SKILL_DIR,
    env_var_for,
    load_mcp_config,
    load_skill,
    playwright_server,
    reference_toolset,
    remote_capabilities,
    user_config_from_env,
    user_config_keys,
)

pytestmark = pytest.mark.agents

WORLDVIEW_SKILL_DIR = DEFAULT_PLUGIN_DIR / "skills" / "worldview-assistant"


@pytest.fixture
def fake_plugin(tmp_path: Path) -> Path:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "fake", "userConfig": {"ieso_mcp_key": {}, "vector_db_token": {}, "sde_mcp_key": {}}})
    )
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "cmr": {"type": "http", "url": "https://example.test/cmr/mcp/"},
                    "ieso-validation": {
                        "type": "http",
                        "url": "https://example.test/validation/mcp",
                        "headers": {"Authorization": "Bearer ${user_config.vector_db_token}"},
                    },
                    "sde-search": {
                        "type": "http",
                        "url": "https://example.test/sde/mcp",
                        "headers": {"Authorization": "Bearer ${user_config.sde_mcp_key}"},
                    },
                    "geoui": {
                        "type": "http",
                        "url": "https://example.test/geoui/mcp",
                        "headers": {"Authorization": "Bearer ${user_config.ieso_mcp_key}"},
                    },
                    "playwright": {"type": "stdio", "command": "npx", "args": ["@playwright/mcp@latest"]},
                }
            }
        )
    )
    return tmp_path


# ----------------------------------------------------------------------------- skills


def test_vendored_skills_exist_and_parse():
    wv = load_skill(WORLDVIEW_SKILL_DIR)
    assert wv.name == "worldview-assistant"
    assert wv.body.startswith("# ROLE")
    assert "geo_ui_render_intent_tool" in wv.body and "browser_navigate" in wv.body
    assert "---" not in wv.body[:5]

    mio = load_skill(MIO_SKILL_DIR)
    assert mio.name == "mio-worldviewagent-v2"
    # the export carries two frontmatter blocks; both are stripped
    assert mio.body.startswith("# ROLE")
    assert "worldview_permalink_tool" in mio.body and "browser_" not in mio.body


def test_load_skill_strips_one_or_two_frontmatter_blocks(tmp_path: Path):
    one = tmp_path / "one"
    one.mkdir()
    (one / "SKILL.md").write_text("---\nname: a\ndescription: d\n---\n\n# ROLE\nbody\n")
    two = tmp_path / "two"
    two.mkdir()
    (two / "SKILL.md").write_text("---\nname: a\nmetadata:\n  x: 1\n---\n\n---\nname: b\n---\n\n# ROLE\nbody\n")
    assert load_skill(one).body == "# ROLE\nbody\n"
    assert load_skill(one).name == "a"
    assert load_skill(two).body == "# ROLE\nbody\n"
    assert load_skill(two).name == "a"


def test_reference_toolset_lists_and_reads_within_references_only():
    skill = load_skill(WORLDVIEW_SKILL_DIR)
    toolset = reference_toolset(skill)
    tools = toolset.tools
    assert set(tools) == {"list_references", "read_reference"}

    paths = tools["list_references"].function()
    assert "tools/geo_ui_render_intent_tool/index.md" in paths
    assert "output.md" in paths
    assert all(not p.startswith("/") for p in paths)

    text = tools["read_reference"].function("tools/geo_ui_render_intent_tool/index.md")
    assert "geo_ui_render_intent_tool" in text

    with pytest.raises(ModelRetry, match="outside"):
        tools["read_reference"].function("../SKILL.md")
    with pytest.raises(ModelRetry, match="No reference document"):
        tools["read_reference"].function("tools/nope.md")


# ----------------------------------------------------------------------------- user config


def test_user_config_keys_and_env_names(fake_plugin: Path):
    assert user_config_keys(fake_plugin) == ["ieso_mcp_key", "vector_db_token", "sde_mcp_key"]
    assert env_var_for("ieso_mcp_key") == "IESO_MCP_KEY"
    assert env_var_for("vector_db_token") == "VECTOR_DB_TOOL_KEY"  # alias kept from the poster-era .env
    assert env_var_for("sde_mcp_key") == "SDE_MCP_KEY"


def test_user_config_from_env_treats_empty_as_unset(fake_plugin: Path):
    env = {"IESO_MCP_KEY": "k1", "VECTOR_DB_TOOL_KEY": ""}
    assert user_config_from_env(fake_plugin, env) == {
        "ieso_mcp_key": "k1",
        "vector_db_token": None,
        "sde_mcp_key": None,
    }


def test_real_plugin_declares_the_expected_user_config_keys():
    assert user_config_keys(DEFAULT_PLUGIN_DIR) == ["ieso_mcp_key", "vector_db_token", "sde_mcp_key", "eonet_token"]


# ----------------------------------------------------------------------------- mcp config


def test_load_mcp_config_substitutes_and_drops_servers_with_missing_keys(fake_plugin: Path, caplog):
    user_config = {"ieso_mcp_key": "ieso-token", "vector_db_token": None, "sde_mcp_key": "sde-token"}
    with caplog.at_level("WARNING", logger="worldview.plugin"):
        servers = load_mcp_config(fake_plugin, user_config=user_config)

    assert set(servers) == {"cmr", "sde-search", "geoui", "playwright"}
    assert "ieso-validation" not in servers
    assert "VECTOR_DB_TOOL_KEY" in caplog.text

    sde = servers["sde-search"]
    assert isinstance(sde, MCPServerStreamableHTTP)
    assert sde.url == "https://example.test/sde/mcp"
    assert sde.headers == {"Authorization": "Bearer sde-token"}
    assert sde.id == "sde-search"
    assert sde.tool_prefix is None
    assert sde.timeout == plugin.REMOTE_MCP_INIT_TIMEOUT_S

    cmr = servers["cmr"]
    assert isinstance(cmr, MCPServerStreamableHTTP)
    assert cmr.url.endswith("/mcp/")  # trailing slash preserved
    assert isinstance(servers["playwright"], MCPServerStdio)


def test_real_plugin_config_loads_with_no_keys_at_all():
    servers = load_mcp_config(DEFAULT_PLUGIN_DIR, user_config=user_config_from_env(DEFAULT_PLUGIN_DIR, {}))
    # only the servers that need no secret survive
    assert set(servers) == {"cmr", "playwright"}


def test_real_plugin_config_loads_with_all_keys():
    fake_env = {env_var_for(k): f"token-{k}" for k in user_config_keys(DEFAULT_PLUGIN_DIR)}
    servers = load_mcp_config(DEFAULT_PLUGIN_DIR, user_config=user_config_from_env(DEFAULT_PLUGIN_DIR, fake_env))
    assert {
        "cmr",
        "ieso-validation",
        "geoui",
        "worldview-permalink",
        "umm-vis-lookup",
        "earthdata-search",
        "pdf-parser",
        "sde-search",
        "eonet",
        "playwright",
    } <= set(servers)
    assert servers["ieso-validation"].headers == {"Authorization": "Bearer token-vector_db_token"}


def test_remote_capabilities_skip_local_servers(fake_plugin: Path):
    user_config = {"ieso_mcp_key": "k", "vector_db_token": "v", "sde_mcp_key": "s"}
    servers = load_mcp_config(fake_plugin, user_config=user_config)
    caps = remote_capabilities(servers)
    assert [c.id for c in caps] == ["cmr", "ieso-validation", "sde-search"]
    assert all(c.native is False and c.local is servers[c.id] for c in caps)


def test_playwright_server_appends_cdp_endpoint(fake_plugin: Path):
    servers = load_mcp_config(
        fake_plugin, user_config={"ieso_mcp_key": "k", "vector_db_token": "v", "sde_mcp_key": "s"}
    )
    attached = playwright_server(servers, "http://localhost:9222")
    assert attached.command == "npx"
    assert list(attached.args) == ["@playwright/mcp@latest", "--cdp-endpoint", "http://localhost:9222"]
    assert attached.timeout == plugin.REMOTE_MCP_INIT_TIMEOUT_S

    fresh = playwright_server(servers, None)
    assert list(fresh.args) == ["@playwright/mcp@latest"]
    assert fresh is not attached

    tuned = playwright_server(servers, "http://localhost:9222", extra_args=["--timeout-action", "15000"], max_retries=3)
    assert list(tuned.args)[-4:] == ["--cdp-endpoint", "http://localhost:9222", "--timeout-action", "15000"]
    assert tuned.max_retries == 3 and attached.max_retries == 1


def test_plugin_dir_env_override_and_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WORLDVIEW_PLUGIN_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="WORLDVIEW_PLUGIN_DIR"):
        plugin.plugin_dir()
    monkeypatch.delenv("WORLDVIEW_PLUGIN_DIR")
    assert plugin.plugin_dir() == DEFAULT_PLUGIN_DIR
