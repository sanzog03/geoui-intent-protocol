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
| `demo/worldview/tools/` | The two protocol operations as plain async functions plus request/response models; `akd.py` wraps them as akd `BaseTool`s | adapter; akd-ext for `akd.py` |
| `demo/worldview/mcp/` | FastMCP server exposing `geo_ui_render_intent_tool` and `geo_ui_get_state_tool`; CLI `worldview-mcp` | fastmcp |
| `demo/worldview/agents/` | IESO Worldview reference agents (GeoUI treatment, VLM baseline), MCP warm-up, benchmark logger | akd-ext, pydantic-ai |
| `demo/worldview/tests/` | Tests for the adapter, tools, MCP contract and agents | — |
| `demo/chat.py`, `demo/start.sh` | One marimo chat notebook for both agents (`AGENT=geoui\|vlm`) and the launcher (Chromium over CDP + notebook) | marimo |
| `tests/` | Library tests (`test_core.py`) and repo-level checks | — |
| `benchmarks/` | Prompt suite, workflow scripts, frozen poster run logs | — |
| `docs/spec.md` | GeoUI Protocol v1.0.0 specification | — |
| `docs/poster/` | Poster narrative, abstract, interaction diagrams, results chart | — |
| `scripts/dump_mcp_contract.py` | Print any MCP server's tool contract as JSON, for diffing | fastmcp |

Importing `geoui` pulls in nothing from `worldview`, akd or fastmcp. The
generic adapter and MCP layer that will eventually live in `geoui` are not
written yet; until then every application-specific piece stays under `demo/`.

## Install

```bash
# the library only (pydantic is its single dependency)
uv add "geoui-protocol @ git+https://github.com/NASA-IMPACT/geoui-intent-protocol"
```

Developing in this repo:

```bash
uv sync    # library + Worldview demo (installs akd-ext from git) + dev tools, in one venv
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

The Claude plugin that consumes this server is `worldview-assistant`, maintained
in `claude-skills-and-plugins/plugins/worldview-assistant` (not part of this repo).

## Agents, benchmark and demo

```bash
uv sync
cp .env.example .env            # OPENAI_API_KEY, VECTOR_DB_TOOL_KEY
./demo/start.sh                 # GeoUI treatment: Chromium + marimo chat
AGENT=vlm ./demo/start.sh       # VLM + browser-control baseline
```

Each chat turn appends a record to `benchmarks/runs.jsonl` (errors to
`benchmarks/errors.jsonl`). The runs behind the poster are frozen under
`benchmarks/results/poster-2026-05/`. The prompt suite is `benchmarks/prompts.md`
and the scenario scripts are `benchmarks/workflows.md`. `HANDOVER.md` has the
operational detail, including the Playwright-over-CDP design and known gotchas.

## Tests

```bash
uv run pytest                      # library + demo (tests/ and demo/worldview/tests/)
uv run pytest -m "not integration" # skip the stdio subprocess smoke
uv run pytest -m agents            # agent-tool parity and the model-visible surface golden
```

## Status and roadmap

Research prototype. Open items, in rough priority order:

- Benchmark is four hand-curated workflows with no variance; add an aggregator and push `n`.
- Accuracy evidence is one worked example; log a question-and-answer set.
- No runnable conformance harness for new adapters (round-trip identity, read-only `get_state`, idempotent `render_intent`, declared extensions match the adapter, layer IDs validated).
- No second adapter; the `geoui.org` extension URIs are placeholders.
- Browser control sits outside the protocol today (Playwright navigates to the URL `render_intent` returns).

## License

Apache-2.0. Lead author Sanjog Thapa (NASA ODSI / UAH).
