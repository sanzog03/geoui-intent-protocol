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

| Path | What it is | Depends on |
|---|---|---|
| `geoui/core.py`, `geoui/extensions/` | The protocol: `GeoIntent`, `Viewport`, `TimeWindow`, `LayerRef`; `compare`, `chart`, `raster-styling` extensions | pydantic |
| `geoui/adapters/worldview/` | Reference adapter: `GeoIntent` ⇄ Worldview permalink URL | pydantic, dateutil |
| `geoui/tools.py` | The two protocol operations as plain async functions plus request/response models | pydantic |
| `geoui/mcp/` | FastMCP server exposing `geo_ui_render_intent_tool` and `geo_ui_get_state_tool` | extra `mcp` |
| `geoui/agents/` | IESO Worldview reference agents (GeoUI treatment, VLM baseline), MCP warm-up, benchmark logger | extra `agents` (akd-ext) |
| `demo/` | `chat.py`, one marimo chat notebook for both agents (`AGENT=geoui\|vlm`), and `start.sh` (Chromium over CDP + notebook) | extra `agents` |
| `benchmarks/` | Prompt suite, workflow scripts, frozen poster run logs | — |
| `docs/spec.md` | GeoUI Protocol v1.0.0 specification | — |
| `docs/poster/` | Poster narrative, abstract, interaction diagrams, results chart | — |
| `scripts/dump_mcp_contract.py` | Print any MCP server's tool contract as JSON, for diffing | extra `mcp` |

Importing `geoui` or `geoui.adapters.worldview` pulls in neither akd nor fastmcp.

## Install

```bash
# library + Worldview adapter
uv add "geoui-protocol @ git+https://github.com/NASA-IMPACT/geoui-intent-protocol"

# with the MCP server
uv add "geoui-protocol[mcp] @ git+https://github.com/NASA-IMPACT/geoui-intent-protocol"
```

Developing in this repo:

```bash
uv sync                  # core + dev tools (includes the mcp extra)
uv sync --extra agents   # also the agents / demo layer (installs akd-ext from git)
```

## Quickstart

```python
from geoui import GeoIntent, LayerRef, TimeWindow, Viewport
from geoui.adapters.worldview import intent_to_url, url_to_intent
from geoui.extensions import compare

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
uv run geoui-mcp                              # stdio
uv run geoui-mcp --transport http --port 8000 # streamable HTTP at /mcp
```

Claude Code / Claude Desktop `.mcp.json` entry for a local server:

```json
{ "mcpServers": { "geoui": { "command": "uv", "args": ["run", "--directory", "/path/to/geoui_intent_protocol", "geoui-mcp"] } } }
```

The server exposes exactly the two protocol tools with the same names, input
schemas and descriptions as the original akd-ext deployment
(`https://sudden-gold-carp-feature-geoui-mcp-tools.fastmcp.app/mcp`), so it is a
drop-in replacement. `tests/mcp/` asserts that contract against a golden
fixture. `fastmcp.json` at the repo root lets FastMCP Cloud (or `fastmcp run`)
deploy it directly.

The Claude plugin that consumes this server is `worldview-assistant`, maintained
in `claude-skills-and-plugins/plugins/worldview-assistant` (not part of this repo).

## Agents, benchmark and demo

```bash
uv sync --extra agents
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
uv run pytest                      # everything available (agents tests skip without akd)
uv run pytest -m "not integration" # skip the stdio subprocess smoke
uv run --extra agents pytest -m agents   # agent-tool parity
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
