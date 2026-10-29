# Contributing

## Setup

```bash
git submodule update --init  # demo/worldview/agents/artifact/worldview/geoui/akd-plugins (the worldview-assistant plugin)
uv sync                      # library + both demos (Worldview, MapLibre) + benchmark utility + dev tools
npm install                  # @geoui/react SDK + MapLibre demo (Node 20+)
uv run pre-commit install    # optional
```

Python 3.12+. The repo is a uv workspace with three projects: `geoui-protocol`
(root, import `geoui`), `geoui-demos` (`demo/`, imports `worldview` and
`maplibre`: the two demos, the latter being the GeoUI MCP over CDP plus its
agent) and `geouibench` (`benchmarks/`, the deepeval benchmark utility). The
two demos share one member because uv refuses a member nested inside another
member's directory. Benchmark app directories such as `benchmarks/worldview/`
are not packages; the utility loads their `app.py` by path. One `uv.lock`
covers all three; commit it. Run every `uv` command from the repo root. The
TypeScript side is an npm workspace (`sdk/geoui-react-adapter`,
`demo/maplibre/maplibre_geo_application`) with one `package-lock.json`; commit it.

## Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest                        # all four projects, no keys, no network
uv run pytest -m "not integration"   # skip the stdio subprocess smoke tests
uv run python scripts/export_schemas.py --check   # schemas/ matches the pydantic models
npm test && npm run lint && npm run build         # SDK (vitest, jsdom) and the MapLibre app (tsc + vite)
```

pytest never needs node and `npm test` never needs Python: the schema contract
is checked on both sides from the committed `schemas/` files
(`tests/test_schemas.py`, `sdk/geoui-react-adapter/src/__tests__/schemas.test.ts`).
After changing a pydantic model: `uv run python scripts/export_schemas.py`,
then `npm run gen:types`, and commit both outputs.

Markers: `integration` (spawns a subprocess or touches the network), `agents`
(needs the demo project and the plugin submodule).

## Layering rules

1. `geoui` (core and extensions) imports only pydantic and the standard
   library. Nothing in `geoui` may import `worldview`. The README import check
   relies on this.
2. `worldview.adapter` imports `geoui` and dateutil. `worldview.tools` imports
   the adapter; `worldview.tools.pai` additionally imports pydantic-ai.
3. `worldview.mcp` may import fastmcp. It must not import `worldview.agents`.
   `server.py` uses absolute `worldview.*` imports because FastMCP loads it as
   a standalone file.
4. `worldview.plugin` and `worldview.agents` import pydantic-ai. Nothing
   imports akd or akd-ext; `test_agent_surface.py::test_no_akd_anywhere`
   enforces it.
5. The two tool names, their parameter names and their descriptions are a
   public contract shared by the MCP server, the pydantic-ai toolset and the
   benchmark logs. Change them only deliberately, and update
   `demo/worldview/tests/mcp/fixtures/akd_contract.json` in the same commit.
6. Prompts are not written in this repo. The GeoUI agent's system prompt is
   the plugin's `SKILL.md` (bump the submodule to change it); the baseline's
   is the vendored `demo/worldview/agents/artifact/worldview/vlm/mio-worldviewagent-v2/SKILL.md` (re-export to
   change it) plus `VLM_BROWSER_ADDENDUM` in `vlm_agent.py`. Everything the
   model sees (prompts, tool descriptions and schemas, output tool names,
   capability ids, browser allow-lists) is pinned by
   `demo/worldview/tests/agents/test_agent_surface.py`; regenerate its fixture
   with `scripts/capture_agent_surface.py` only for intentional changes and
   review the diff.
7. Secrets never enter the repo. The plugin's `.mcp.json` uses
   `${user_config.*}` placeholders; the loader fills them from the
   environment at run time. Do not vendor a plugin copy with literal tokens.
8. `demo/chat.py` stays at `demo/`, not inside `demo/worldview/`. marimo puts
   the notebook's directory at the front of `sys.path`; from inside the
   package that would shadow the installed `mcp` SDK and `agents` packages.
9. Dependency direction of the benchmark: `geoui` ← `geouibench` ←
   `benchmarks/<app>/app.py` → the app's demo package. `geouibench` knows
   pydantic-ai, deepeval and the `GeoIntent` vocabulary and nothing about any
   application or about how an agent acts: no application name appears in it,
   its docs or its tests. `demo/` never imports `geouibench` or deepeval (the
   README import check covers it). deepeval's pytest plugin stays blocked in the
   unit suite (`-p no:deepeval`); only `deepeval test run` enables it.
10. `maplibre` imports `geoui`, playwright, fastmcp and pydantic-ai and
    never `worldview`: its tools know no application, the page's
    `window.geoui.describe()` says what is supported, and only the agent's
    prompt names MapLibre. The app (`demo/maplibre/maplibre_geo_application`)
    imports only `@geoui/react` (through the Vite alias to its source). The three tool
    names are the same as the Worldview server's (rule 5); the bridge's
    contract golden is `demo/maplibre/tests/mcp/fixtures/bridge_contract.json`
    (`scripts/dump_mcp_contract.py local --module maplibre.mcp.server:mcp
    --golden <that path> --update-golden`).
11. Agent-facing wording is shared across the boundary on purpose: the SDK's
    `validate()` messages (`sdk/geoui-react-adapter/src/errors.ts`) mirror
    `prepare_intent` in `maplibre.catalogue` and `worldview.tools`. Change
    them together.

## Adding an adapter

Two paths exist. **A React app** attaches its state with `@geoui/react`
(`GeoUIProvider` + the attach hooks, see `demo/maplibre/maplibre_geo_application/src/App.tsx`), publishes
its layer catalogue through the provider's `layers` prop, and is driven by
`maplibre-mcp` with no Python code of its own; benchmark it with a
`benchmarks/<name>/app.py` modelled on `benchmarks/maplibre/app.py`. **A
URL-state application** gets a Python adapter: `geoui` has no generic adapter
interface yet; each such application is its own workspace member under
`demo/`, mirroring `demo/worldview/`. Create
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

## Changing the benchmark

- **Add a gold scenario:** append an object to
  `benchmarks/worldview/datasets/gold_dataset.json` with both `openers`
  (layer-id wording for `geoui`, searchable-name wording for `vlm`), the
  ordered follow-up steps in `scenario`, an `expected_state` (and
  `checkpoints` for multi-turn workflows), `max_user_simulations` and
  `state_threshold`. `uv run pytest benchmarks/worldview/tests` validates it.
- **Regenerate the synthetic set:** `uv run python -m geouibench synthetic
  benchmarks/worldview` (the wording lives in `SYNTHETIC_STYLE` in `app.py`);
  review the output before committing it.
- **The live eval file is `benchmarks/geouibench/evals/test_benchmark.py`**
  and is not in `testpaths`; it skips itself unless `BENCHMARK_APP` and
  `BENCHMARK_RUN` are set, which `python -m geouibench run` sets. Never add it
  to `testpaths`.
- **Commit results deliberately:** `run` writes
  `benchmarks/<app>/results/<run-id>/`; commit the folder with its
  `summary.md`. The artifact test fails on absolute paths.
- **Bind another application:** a new directory `benchmarks/<name>/` with an
  `app.py` (`APP` satisfying `geouibench.BenchmarkApp`, optionally `prepare()`,
  `snapshot()` for apps whose state is not a URL, and `SYNTHETIC_STYLE`) and a
  gold dataset. No package, no eval file, no script. See `benchmarks/README.md`
  and, for the page-state pattern, `benchmarks/maplibre/`.

## Adding an extension

Create `geoui/extensions/<name>.py` defining `URI`, `PREFIX`, a typed
`<Name>Fields` model, and `extract` / `inject` / `validate`, mirroring
`compare.py`. Declaring and using must agree: fields present without the URI
in `geoui_extensions` (or vice versa) raise. Bump the extension's version in
its URI on breaking changes; see `docs/spec.md`.
