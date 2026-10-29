# GeoUI Intent Protocol

An application-agnostic, typed, declarative description of a geospatial
visualization state that an LLM agent reads and writes **instead of driving
screenshots, DOM trees or clicks**. The agent emits a `GeoIntent` (viewport,
time, layers, plus opt-in extensions); a thin adapter translates it to and
from the target application's native state. The application itself is never
modified.

On iterative NASA Worldview workflows the protocol path was roughly an order
of magnitude cheaper per task than a vision-language-model plus browser-control
baseline, and it answered correctly on questions the baseline could not
(Worldview renders through canvas and WebGL, so semantic map state is not
recoverable from pixels). See [`docs/poster/`](docs/poster/) for the poster
presented at the 2nd ESA-NASA International Workshop on AI Foundation Models
for Earth Observation (NASA MSFC, May 2026).

## Layout

Four projects in one uv workspace, plus an npm workspace. `geoui-protocol`
(import `geoui`) is the library and depends on pydantic alone.
`geoui-worldview-demo` (import `worldview`, under `demo/`) is the NASA
Worldview reference implementation and carries everything Worldview-specific.
`geoui-bridge` (import `geoui_bridge`, under `bridge/`) is the GeoUI MCP for
any page that exposes `window.geoui`, and `geouibench` (`benchmarks/`) is the
benchmark utility. On the TypeScript side, `@geoui/react` (`sdk/geoui-react`)
is the adapter SDK for React apps and `demo/maplibre` is a map app built with
it.

| Path | What it is | Depends on |
|---|---|---|
| `geoui/core.py`, `geoui/extensions/` | **The protocol.** `GeoIntent`, `Viewport`, `TimeWindow`, `LayerRef`; `compare`, `chart`, `raster-styling` extensions; `ExtensionSpec` (`describe()`, `declare`, `used_prefixes`) for consumers that advertise what they support | pydantic |
| `schemas/`, `scripts/export_schemas.py` | The protocol's JSON Schemas (core + one `describe()` document per extension), exported from the pydantic models and drift-checked by `tests/test_schemas.py`; what non-Python consumers read | — |
| `demo/pyproject.toml` | The demo project (`geoui-worldview-demo`), a uv workspace member installed editable by `uv sync` | geoui-protocol |
| `demo/worldview/adapter/` | Reference adapter: `GeoIntent` ⇄ Worldview permalink URL (`mapping.py`, `permalink.py`, `url_parser.py`) | geoui, dateutil |
| `demo/worldview/tools/` | The two protocol operations as plain async functions plus request/response models; `pai.py` exposes them (and `worldview_permalink_tool`) as pydantic-ai toolsets | adapter; pydantic-ai for `pai.py` |
| `demo/worldview/mcp/` | FastMCP server exposing `geo_ui_render_intent_tool` and `geo_ui_get_state_tool`; CLI `worldview-mcp` | fastmcp |
| `demo/worldview/plugin.py` | Loads a Claude Code plugin for pydantic-ai: `SKILL.md` as system prompt, `references/` behind `read_reference`, `.mcp.json` servers with `${user_config.*}` filled from the environment | pydantic-ai |
| `demo/worldview/agents/` | The two agents as bare pydantic-ai `Agent`s built from the plugin skills (GeoUI treatment, VLM baseline), MCP warm-up, benchmark logger | pydantic-ai |
| `demo/worldview/agents/artifact/worldview/geoui/akd-plugins/` | git submodule of [NASA-IMPACT/akd-plugins](https://github.com/NASA-IMPACT/akd-plugins); the `worldview-assistant` plugin is the GeoUI agent's skill and MCP server list | — |
| `demo/worldview/agents/artifact/worldview/vlm/mio-worldviewagent-v2/` | Vendored non-GeoUI skill (`SKILL.md` + `references/`) the baseline agent runs | — |
| `demo/worldview/tests/` | Tests for the adapter, tools, MCP contract, plugin loader and agents | — |
| `demo/chat.py`, `demo/start.sh`, `demo/chromium.sh` | One marimo chat notebook for all three agents (`AGENT=geoui\|vlm\|maplibre`), the launcher, and the Chromium-over-CDP helper it shares with the benchmarks | marimo |
| `sdk/geoui-react/` | **`@geoui/react`**, the adapter SDK for React apps: `GeoUIProvider`, attach hooks (`useGeoUIViewport` / `Time` / `Layers` / `Extension` / `LayerExtension`), a registry that composes and applies a `GeoIntent`, and `window.geoui` (`describe` / `getState` / `render`). Types and extension specs are generated from `schemas/` | react (peer) |
| `demo/maplibre/` | A React + MapLibre + NASA GIBS map app with the SDK attached: nothing in the URL; an agent drives it through `window.geoui`. `npm run dev -w demo/maplibre` | @geoui/react, react-map-gl |
| `bridge/` | **`geoui-bridge`** (import `geoui_bridge`): the GeoUI MCP over CDP for any `window.geoui` page. `cdp.py` (Playwright `connect_over_cdp` session), `catalogue.py` (the page's catalogue checked against the library, consumer-side pre-declaration), `tools/` (the three tools; `pai.py` as a pydantic-ai toolset), `mcp/server.py` (`geoui-bridge-mcp`), `agents/maplibre_agent.py` | geoui, playwright, fastmcp, pydantic-ai |
| `tests/` | Library tests (`test_core.py`) and repo-level checks | — |
| `benchmarks/geouibench/` | `geouibench`: the benchmark utility (simulated multi-turn user, per-turn traces, six metrics, synthetic goldens, offline re-scoring, cross-agent summary, `python -m geouibench` CLI); names no application | deepeval, pydantic-ai |
| `benchmarks/worldview/` | The Worldview app directory for `geouibench`: `app.py` (both agents, state read-back, prepare hook), gold + synthetic datasets, committed results per run | geouibench, demo |
| `benchmarks/maplibre/` | The MapLibre app directory for `geouibench`: `app.py` (the bridge's agent, state read from the page as a `geoui+json` handle), the gold set without chart, committed results | geouibench, geoui-bridge |
| `benchmarks/worldview_legacy/` | The earlier notebook-driven procedure: prompt suite, workflow scripts, frozen poster run logs | — |
| `docs/spec.md` | GeoUI Protocol v1.0.0 specification | — |
| `docs/poster/` | Poster narrative, abstract, interaction diagrams, results chart | — |
| `docs/maplibre-demo/architecture.md` | Component, sequence and deployment diagrams of the agent → MCP → CDP → SDK → app path | — |
| `scripts/dump_mcp_contract.py` | Print any MCP server's tool contract as JSON, for diffing | fastmcp |

Importing `geoui` pulls in nothing from `worldview`, `geoui_bridge`,
pydantic-ai or fastmcp. Two adapter paths exist today: the Worldview adapter
(Python, URL-based, under `demo/worldview`) and the React SDK + CDP bridge
(for apps whose state is not in a URL); the shared Python interface they will
eventually meet in is not lifted into `geoui` yet.

## Install

```bash
# the library only (pydantic is its single dependency)
uv add "geoui-protocol @ git+https://github.com/NASA-IMPACT/geoui-intent-protocol"
```

Developing in this repo:

```bash
git clone --recurse-submodules https://github.com/NASA-IMPACT/geoui-intent-protocol   # or: git submodule update --init
uv sync    # library + Worldview demo + CDP bridge + benchmark utility + dev tools, in one venv
npm install   # the @geoui/react SDK and the MapLibre demo (Node 20+)
```

`uv sync --no-dev` installs the library alone.

## MapLibre demo: an application with no URL state

```bash
npm run dev -w demo/maplibre                        # the app at http://127.0.0.1:5173
source demo/chromium.sh && ensure_chromium          # Chromium with CDP on :9222
GEOUI_APP_URL=http://127.0.0.1:5173 uv run geoui-bridge-mcp   # the GeoUI MCP (stdio), e.g. from Claude Code
uv run python -m geoui_bridge.agents.maplibre_agent "Show MODIS Aqua AOD over California on 2025-09-15"
AGENT=maplibre ./demo/start.sh                      # the marimo chat notebook on the MapLibre agent
uv run python -m geouibench run benchmarks/maplibre gold --smoke --run-id smoke
```

The app attaches its state with the `@geoui/react` hooks and exposes
`window.geoui`; the bridge attaches to Chromium over CDP, reads the page's
extension catalogue, pre-declares the supported URIs and renders intents with
`page.evaluate`. The same three tools, the same benchmark: see
[`docs/maplibre-demo/architecture.md`](docs/maplibre-demo/architecture.md).

## Quickstart

With the demo installed (`uv sync`):

```python
from geoui import GeoIntent, LayerRef, TimeWindow, Viewport
from geoui.extensions import compare
from worldview.adapter import intent_to_url, url_to_intent

intent = GeoIntent(
    viewport=Viewport(bbox=[-125, 32, -114, 42], crs="EPSG:4326"),
    time=TimeWindow(instant="2025-09-15"),
    layers=[LayerRef(id="MODIS_Aqua_Aerosol_Optical_Depth_3km", opacity=0.8)],
)
intent = compare.inject(
    intent, compare.CompareFields(layers=[LayerRef(id="MODIS_Aqua_Aerosol_Optical_Depth_3km")], mode="swipe")
)

url = intent_to_url(intent)  # render: agent → app
state = url_to_intent(url)  # observe: app → agent (same shape back)
assert compare.extract(state).mode == "swipe"
```

## MCP server

```bash
uv run worldview-mcp                              # stdio
uv run worldview-mcp --transport http --port 8000 # streamable HTTP at /mcp
```

Claude Code / Claude Desktop `.mcp.json` entry for a local server:

```json
{ "mcpServers": { "geoui": { "command": "uv", "args": ["run", "--directory", "/path/to/geoui_intent_protocol", "worldview-mcp"] } } }
```

The server exposes the two protocol tools, `geo_ui_render_intent_tool` and
`geo_ui_get_state_tool`, with the same names and shapes as the original akd-ext
deployment (`https://sudden-gold-carp-feature-geoui-mcp-tools.fastmcp.app/mcp`),
plus `geo_ui_list_intent_extensions_tool`, the deployment's extension catalogue.
Extensions are pre-declared: the render tool lists the adapter's supported
extensions in its description, adds their URIs to every incoming intent and
refuses fields of any other namespace, so an agent only decides which
extensions a request needs and fills their fields. `demo/worldview/tests/mcp/`
asserts that contract against a golden fixture. `fastmcp.json` at the repo root points FastMCP Cloud (or
`fastmcp run`) at `demo/worldview/mcp/server.py:mcp`.

The Claude Code plugin that consumes this server is `worldview-assistant` from
[NASA-IMPACT/akd-plugins](https://github.com/NASA-IMPACT/akd-plugins), vendored
here as the `demo/worldview/agents/artifact/worldview/geoui/akd-plugins` submodule because the demo agents run the
same skill and MCP server list (see below).

## Agents, benchmark and demo

Two bare pydantic-ai agents, each driven by a Claude Code skill so Claude Code
users and the demo share one source of truth:

| `AGENT` | Skill (system prompt) | Tools | Browser |
|---|---|---|---|
| `geoui` | `worldview-assistant` from the plugin submodule | GeoUI protocol tools in-process, `worldview_permalink_tool`, the plugin's remote discovery MCPs, `read_reference` over the skill's `references/` | `browser_navigate` + `browser_evaluate` only: open the rendered URL, read the live one back |
| `vlm` | `mio-worldviewagent-v2` (vendored, no GeoUI) plus a browser addendum | `worldview_permalink_tool`, the same discovery MCPs, `read_reference` | Eleven Playwright tools: snapshot, screenshot, click, type, drag, ... |

The plugin's `.mcp.json` references its secrets as `${user_config.*}`; the
loader fills them from `.env` (`VECTOR_DB_TOOL_KEY`, `IESO_MCP_KEY`,
`SDE_MCP_KEY`, `EONET_TOKEN`) and skips, with a warning, any server whose key
is unset. The `geoui` and `worldview-permalink` servers are always replaced by
the in-process implementations from this repo.

```bash
uv sync
cp .env.example .env            # OPENAI_API_KEY, then the MCP keys you have
./demo/start.sh                 # GeoUI treatment: Chromium + marimo chat
AGENT=vlm ./demo/start.sh       # VLM + browser-control baseline
```

Each chat turn appends a record to `benchmarks/worldview_legacy/runs.jsonl` (errors to
`benchmarks/worldview_legacy/errors.jsonl`); that notebook-driven procedure, its prompt
suite and the frozen poster logs live under `benchmarks/worldview_legacy/`.

## Benchmark

The re-runnable comparison lives in `benchmarks/`: `geouibench`
(`benchmarks/geouibench/`) is a mechanism-neutral deepeval benchmark utility, and
`benchmarks/worldview/` is the app directory that binds both agents to it. deepeval's
`ConversationSimulator` plays the user (the first turn verbatim per agent, the
follow-ups improvised from the scenario), every turn is traced, and six
metrics score each conversation: success (final UI state vs the expected
state), completion, tool / time / token efficiency, and turn relevancy. The
summary lays the two agents side by side with VLM ÷ GeoUI ratios.

```bash
uv run python -m geouibench run benchmarks/worldview gold --smoke --run-id smoke   # one scenario, both agents
uv run python -m geouibench run benchmarks/worldview gold --run-id 2026-10-28-gold # the full gold set
uv run python -m geouibench score benchmarks/worldview/results/2026-10-28-gold     # re-score from committed traces, no agent
```

Benchmarking another demo is an `app.py` plus a gold dataset in a new directory
under `benchmarks/`; see `benchmarks/README.md` (the utility, the app contract,
dataset format, metrics, how traces are captured), `benchmarks/geouibench/README.md`
(every utility and how to call it) and
`benchmarks/worldview/README.md` (running, reading and verifying a Worldview run).
`HANDOVER.md` has the operational detail, including the Playwright-over-CDP design
and known gotchas.

## Tests

```bash
uv run pytest                      # library + demo + benchmark utility + Worldview app tests, offline
uv run pytest -m "not integration" # skip the stdio subprocess smoke
uv run pytest -m agents            # plugin loader, toolset parity and the model-visible surface golden
```

## Status and roadmap

Research prototype. Open items, in rough priority order:

- The benchmark's gold set is eight hand-curated scenarios and one synthetic set; push `n` and add scenarios beyond the compare/chart/styling extensions.
- Accuracy evidence is one worked example; log a question-and-answer set.
- No runnable conformance harness for new adapters (round-trip identity, read-only `get_state`, idempotent `render_intent`, declared extensions match the adapter, layer IDs validated).
- No second adapter; the `geoui.org` extension URIs are placeholders.
- Browser control sits outside the protocol today (Playwright navigates to the URL `render_intent` returns).

## License

Apache-2.0. Lead author Sanjog Thapa (NASA ODSI / UAH).
