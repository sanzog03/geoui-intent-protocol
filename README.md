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

Two projects in one uv workspace. `geoui-protocol` (import `geoui`) is the
library and depends on pydantic alone. `geoui-worldview-demo` (import
`worldview`, under `demo/`) is the NASA Worldview reference implementation and
carries everything application-specific.

| Path | What it is | Depends on |
|---|---|---|
| `geoui/core.py`, `geoui/extensions/` | **The protocol.** `GeoIntent`, `Viewport`, `TimeWindow`, `LayerRef`; `compare`, `chart`, `raster-styling` extensions | pydantic |
| `demo/pyproject.toml` | The demo project (`geoui-worldview-demo`), a uv workspace member installed editable by `uv sync` | geoui-protocol |
| `demo/worldview/adapter/` | Reference adapter: `GeoIntent` ⇄ Worldview permalink URL (`mapping.py`, `permalink.py`, `url_parser.py`) | geoui, dateutil |
| `demo/worldview/tools/` | The two protocol operations as plain async functions plus request/response models; `pai.py` exposes them (and `worldview_permalink_tool`) as pydantic-ai toolsets | adapter; pydantic-ai for `pai.py` |
| `demo/worldview/mcp/` | FastMCP server exposing `geo_ui_render_intent_tool` and `geo_ui_get_state_tool`; CLI `worldview-mcp` | fastmcp |
| `demo/worldview/plugin.py` | Loads a Claude Code plugin for pydantic-ai: `SKILL.md` as system prompt, `references/` behind `read_reference`, `.mcp.json` servers with `${user_config.*}` filled from the environment | pydantic-ai |
| `demo/worldview/agents/` | The two agents as bare pydantic-ai `Agent`s built from the plugin skills (GeoUI treatment, VLM baseline), MCP warm-up, benchmark logger | pydantic-ai |
| `demo/worldview/agents/artifact/worldview/geoui/akd-plugins/` | git submodule of [NASA-IMPACT/akd-plugins](https://github.com/NASA-IMPACT/akd-plugins); the `worldview-assistant` plugin is the GeoUI agent's skill and MCP server list | — |
| `demo/worldview/agents/artifact/worldview/vlm/mio-worldviewagent-v2/` | Vendored non-GeoUI skill (`SKILL.md` + `references/`) the baseline agent runs | — |
| `demo/worldview/tests/` | Tests for the adapter, tools, MCP contract, plugin loader and agents | — |
| `demo/chat.py`, `demo/start.sh`, `demo/chromium.sh` | One marimo chat notebook for both agents (`AGENT=geoui\|vlm`), the launcher, and the Chromium-over-CDP helper it shares with the benchmark | marimo |
| `tests/` | Library tests (`test_core.py`) and repo-level checks | — |
| `benchmarks/geouibench/` | `geouibench`: the benchmark utility (simulated multi-turn user, per-turn traces, six metrics, synthetic goldens, offline re-scoring, cross-agent summary, `python -m geouibench` CLI); names no application | deepeval, pydantic-ai |
| `benchmarks/worldview/` | The Worldview app directory for `geouibench`: `app.py` (both agents, state read-back, prepare hook), gold + synthetic datasets, committed results per run | geouibench, demo |
| `benchmarks/manual/` | The earlier notebook-driven procedure: prompt suite, workflow scripts, frozen poster run logs | — |
| `docs/spec.md` | GeoUI Protocol v1.0.0 specification | — |
| `docs/poster/` | Poster narrative, abstract, interaction diagrams, results chart | — |
| `scripts/dump_mcp_contract.py` | Print any MCP server's tool contract as JSON, for diffing | fastmcp |

Importing `geoui` pulls in nothing from `worldview`, pydantic-ai or fastmcp. The
generic adapter and MCP layer that will eventually live in `geoui` are not
written yet; until then every application-specific piece stays under `demo/`.

## Install

```bash
# the library only (pydantic is its single dependency)
uv add "geoui-protocol @ git+https://github.com/NASA-IMPACT/geoui-intent-protocol"
```

Developing in this repo:

```bash
git clone --recurse-submodules https://github.com/NASA-IMPACT/geoui-intent-protocol   # or: git submodule update --init
uv sync    # library + Worldview demo + benchmark harness + dev tools, in one venv
```

`uv sync --no-dev` installs the library alone.

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

The server exposes exactly the two protocol tools with the same names, input
schemas and descriptions as the original akd-ext deployment
(`https://sudden-gold-carp-feature-geoui-mcp-tools.fastmcp.app/mcp`), so it is a
drop-in replacement. `demo/worldview/tests/mcp/` asserts that contract against
a golden fixture. `fastmcp.json` at the repo root points FastMCP Cloud (or
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

Each chat turn appends a record to `benchmarks/manual/runs.jsonl` (errors to
`benchmarks/manual/errors.jsonl`); that notebook-driven procedure, its prompt
suite and the frozen poster logs live under `benchmarks/manual/`.

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
dataset format, metrics, how traces are captured) and
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
