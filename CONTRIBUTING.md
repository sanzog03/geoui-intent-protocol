# Contributing

## Setup

```bash
uv sync                      # core + dev (ruff, pytest, fastmcp)
uv sync --extra agents       # agents / demo layer; installs akd-ext from git (needs GitHub access)
uv run pre-commit install    # optional
```

Python 3.12+. Dependencies are managed with uv; commit `uv.lock`.

## Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest                        # agents tests auto-skip when akd is not installed
uv run pytest -m "not integration"   # skip the stdio subprocess smoke test
```

Markers: `integration` (spawns a subprocess or touches the network), `agents`
(requires the agents extra).

## Layering rules

1. `geoui.core`, `geoui.extensions`, `geoui.adapters.*` and `geoui.tools` must
   import only pydantic and the standard library (plus dateutil in the
   Worldview adapter). `tests/mcp` and the README's import check rely on this.
2. `geoui.mcp` may import fastmcp. It must not import `geoui.agents`.
3. `geoui.agents` may import akd / akd-ext / pydantic-ai. Nothing outside it may.
4. The two tool names, their parameter names and their descriptions are a
   public contract shared by the MCP server, the akd wrappers and the
   benchmark logs. Change them only deliberately, and update
   `tests/mcp/fixtures/akd_contract.json` in the same commit.
5. In `geoui.agents`, model-visible text (system prompts, config
   `description`, output-schema names, docstrings and field descriptions,
   agent class names) lives in `geoui_agent.py` / `vlm_agent.py`; shared
   plumbing lives in `_common.py`. `tests/agents/test_agent_surface.py`
   proves a refactor is prose-neutral; regenerate its fixture with
   `scripts/capture_agent_surface.py` only for intentional changes.

## Adding an adapter

Create `geoui/adapters/<app>/` with:

- `intent_to_<native>(intent: GeoIntent) -> NativeState` and
  `<native>_to_intent(state: NativeState) -> GeoIntent`;
- convenience wrappers equivalent to `intent_to_url` / `url_to_intent`;
- tests under `tests/adapters/<app>/` that prove the round-trip property
  (`intent → native → intent` is the identity on supported fields).

Start with `viewport`, `time` and `layers` only. Add extensions once the core
round-trips cleanly. If the app cannot express an extension field, document
the gap rather than dropping the field silently.

## Adding an extension

Create `geoui/extensions/<name>.py` defining `URI`, `PREFIX`, a typed
`<Name>Fields` model, and `extract` / `inject` / `validate`, mirroring
`compare.py`. Declaring and using must agree: fields present without the URI
in `geoui_extensions` (or vice versa) raise. Bump the extension's version in
its URI on breaking changes; see `docs/spec.md`.
