# Contributing

## Setup

```bash
uv sync                      # library + Worldview demo + dev tools; installs akd-ext from git (needs GitHub access)
uv run pre-commit install    # optional
```

Python 3.12+. The repo is a uv workspace with two projects: `geoui-protocol`
(root, import `geoui`) and `geoui-worldview-demo` (`demo/`, import
`worldview`). One `uv.lock` covers both; commit it. Run every `uv` command from
the repo root.

## Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest                        # agents tests auto-skip when akd is not installed
uv run pytest -m "not integration"   # skip the stdio subprocess smoke test
```

Markers: `integration` (spawns a subprocess or touches the network), `agents`
(requires akd-ext, which `uv sync` installs with the demo).

## Layering rules

1. `geoui` (core and extensions) imports only pydantic and the standard
   library. Nothing in `geoui` may import `worldview`. The README import check
   relies on this.
2. `worldview.adapter` imports `geoui` and dateutil. `worldview.tools` imports
   the adapter; `worldview.tools.akd` additionally imports akd.
3. `worldview.mcp` may import fastmcp. It must not import `worldview.agents`.
   `server.py` uses absolute `worldview.*` imports because FastMCP loads it as
   a standalone file.
4. `worldview.agents` may import akd / akd-ext / pydantic-ai. Nothing outside
   it (and `worldview.tools.akd`) may.
5. The two tool names, their parameter names and their descriptions are a
   public contract shared by the MCP server, the akd wrappers and the
   benchmark logs. Change them only deliberately, and update
   `demo/worldview/tests/mcp/fixtures/akd_contract.json` in the same commit.
6. In `worldview.agents`, model-visible text (system prompts, config
   `description`, output-schema names, docstrings and field descriptions,
   agent class names) lives in `geoui_agent.py` / `vlm_agent.py`; shared
   plumbing lives in `_common.py`. `demo/worldview/tests/agents/test_agent_surface.py`
   proves a refactor is prose-neutral; regenerate its fixture with
   `scripts/capture_agent_surface.py` only for intentional changes.
7. `demo/chat.py` stays at `demo/`, not inside `demo/worldview/`. marimo puts
   the notebook's directory at the front of `sys.path`; from inside the
   package that would shadow the installed `mcp` SDK and `agents` packages.

## Adding an adapter

`geoui` has no generic adapter interface yet; each application is its own
workspace member under `demo/`, mirroring `demo/worldview/`. Create
`demo/<app>/pyproject.toml` and `demo/<app>/<app>/adapter/` with:

- `intent_to_<native>(intent: GeoIntent) -> NativeState` and
  `<native>_to_intent(state: NativeState) -> GeoIntent`;
- convenience wrappers equivalent to `intent_to_url` / `url_to_intent`;
- tests under `demo/<app>/<app>/tests/adapter/` that prove the round-trip
  property (`intent → native → intent` is the identity on supported fields);
- a line in the root `[tool.uv.workspace] members` and in the dev group.

Start with `viewport`, `time` and `layers` only. Add extensions once the core
round-trips cleanly. If the app cannot express an extension field, document
the gap rather than dropping the field silently.

Once two adapters exist, lift the shared interface into `geoui`.

## Adding an extension

Create `geoui/extensions/<name>.py` defining `URI`, `PREFIX`, a typed
`<Name>Fields` model, and `extract` / `inject` / `validate`, mirroring
`compare.py`. Declaring and using must agree: fields present without the URI
in `geoui_extensions` (or vice versa) raise. Bump the extension's version in
its URI on breaking changes; see `docs/spec.md`.
