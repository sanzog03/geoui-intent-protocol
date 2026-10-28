# GeoUI Intent Protocol — Developer Handover

**Status:** research prototype (poster-track benchmark), consolidated into this
standalone repo in October 2026 from an `akd-ext` worktree.
**Read first:** this file top to bottom, then keep §7 (gotchas) and §6 (benchmark)
open while you work. The poster-era narrative is in `docs/poster/HANDOVER.md`.

---

## 1. What this is

The GeoUI Intent Protocol **decouples agent reasoning from app-specific
rendering**. Instead of teaching an LLM the NASA Worldview permalink grammar,
or letting it click around the UI, the agent emits a small, declarative,
application-agnostic document, a `GeoIntent`, describing the *desired map
state*. A pure adapter translates it to and from Worldview's permalink URL.
Thesis: an intent schema is an order of magnitude cheaper (tokens, tool calls,
latency) than driving the UI with a vision-language model, and it stays
reproducible and auditable. The repo ships the protocol, the Worldview
adapter, the two tools (plain functions, an MCP server, and akd wrappers), the
two reference agents, a marimo chat demo, and the head-to-head benchmark.

```
            ┌──────────────────────────────────────────────────────┐
            │  Agent reasons ONLY in GeoIntent (app-agnostic)      │
            └──────────────────────────────────────────────────────┘
                         │  intent                      ▲  intent
                         ▼                              │
  GeoIntent ──► intent_to_url ──► Worldview permalink URL ──► browser_navigate (Playwright/CDP)
       ▲                                  │
       └────── url_to_intent ◄────────────┘  (read current state back for iterative refinement)
```

## 2. Layers and file map

| Path | What it is | Imports |
|---|---|---|
| `docs/spec.md` | GeoUI Protocol v1.0.0 spec (STAC-inspired). The field-level contract. | — |
| `geoui/core.py` | `GeoIntent`, `Viewport`, `TimeWindow`, `LayerRef`, `extension_fields()`. | pydantic |
| `geoui/extensions/{compare,chart,raster_styling}.py` | Each defines `URI`, `PREFIX`, a typed `*Fields` model, `extract` / `inject` / `validate`. | pydantic |
| `demo/worldview/adapter/permalink.py` | Worldview-native side: `LayerSpec`, `WorldviewPermalinkInputSchema`, `build_url`. Copied from akd-ext's permalink tool with the akd `BaseTool` class removed; `build_url` is now a module function. | pydantic, dateutil |
| `demo/worldview/adapter/url_parser.py` | Inverse of `build_url`. Hand-written layer-grammar parser. | — |
| `demo/worldview/adapter/mapping.py` | The **only** module that knows GeoIntent ⇄ Worldview. `intent_to_permalink_input` / `permalink_input_to_intent`, wrappers `intent_to_url` / `url_to_intent`. | — |
| `demo/worldview/tools/__init__.py` | The two operations as async functions, request/response models, and the agent-facing docstrings and field descriptions (single source of truth for all three tool surfaces). | adapter |
| `demo/worldview/mcp/_describe.py` | Rebuilds akd's `INPUT/OUTPUT FIELD DESCRIPTIONS` description suffix so the MCP contract matches the original deployment. | — |
| `demo/worldview/mcp/server.py` | `FastMCP("geoui")` with the two tools; `main()` is the `worldview-mcp` CLI. Absolute `worldview.*` imports only: FastMCP loads this file standalone. | fastmcp |
| `demo/worldview/tools/akd.py` | akd `BaseTool` subclasses the agents pass to `PydanticAIBaseAgentConfig.tools`. Same names and descriptions as the MCP server; protocol `ValueError`s become `SchemaValidationError` so the model gets a retry. | akd |
| `demo/worldview/agents/_common.py` | Plumbing shared by both agents: the two remote MCPs (`get_default_ieso_worldview_capabilities`), the three discovery tools, `make_playwright_mcp` / `playwright_capability` with the two browser allow-lists, the input schema, the structured-output check (`IESOWorldviewAgentBase`) and the `run_smoke` runner. The Playwright/CDP design note lives here. | akd-ext, pydantic-ai |
| `demo/worldview/agents/geoui_agent.py` | `IESOWorldviewGeoUIAgent` (treatment): only what the model sees. Its system prompt, config `description`, output schema, agent class, the GeoUI tool list and the two-tool browser allow-list. | `_common` |
| `demo/worldview/agents/vlm_agent.py` | `IESOWorldviewVLMAgent` (baseline): same shape. Differs in the observe/act steps of the prompt, the tool list (no GeoUI tools) and the eleven-tool browser allow-list. | `_common` |
| `demo/worldview/agents/warm_mcps.py` | Pings each remote MCP once at launch to absorb FastMCP cold starts. | httpx |
| `demo/worldview/agents/benchmark/log.py` | Per-turn JSONL logging (`TurnRecord`, `ErrorRecord`, `append_*`, `load_runs`). | pydantic |
| `demo/start.sh` | Launches a long-lived Chromium with remote debugging, warms MCPs, opens the marimo notebook. `AGENT=geoui` (default) or `vlm`. | uv, npx |
| `demo/chat.py` | One marimo multi-turn chat app for both agents; `AGENT=geoui` (default) or `vlm` picks the agent, intro text, example prompts and benchmark-log label. Carries `run_context` across turns; attaches Playwright per turn via CDP. | marimo |
| `benchmarks/prompts.md`, `benchmarks/workflows.md` | Prompt suite (Core 6 + Optional 4) and 5-turn scenario scripts (A: CA wildfire smoke; B: Saharan dust; C: Lake Erie bloom). | — |
| `benchmarks/results/poster-2026-05/` | Frozen `runs.jsonl` (51 rows) and `errors.jsonl` (22 rows) behind the poster. Absolute paths in tracebacks were replaced (`<worktree>` for the source checkout, `<python>` for the interpreter install). | — |
| `scripts/dump_mcp_contract.py` | Dump any server's tool contract as JSON. | fastmcp |
| `demo/pyproject.toml` | The `geoui-worldview-demo` project: a uv workspace member that depends on `geoui-protocol` and owns the heavy dependencies (akd-ext, pydantic-ai, fastmcp, marimo). The root dev group installs it editable. | — |
| `tests/` | `test_core.py` and `test_benchmark_results.py` (library and repo-level). | — |
| `demo/worldview/tests/` | `adapter/` (permalink, assembly, round trip); `mcp/test_server.py` (contract vs golden, calls, stdio smoke); `agents/test_akd_tools.py` (parity) and `agents/test_agent_surface.py` (model-visible surface golden). Collected by the root `pytest` via `testpaths`. | — |

**Layering rule:** `geoui` imports only pydantic and never `worldview`.
`worldview.adapter` adds dateutil; `worldview.tools` the adapter;
`worldview.mcp` fastmcp; `worldview.agents` and `worldview.tools.akd` akd /
akd-ext / pydantic-ai. The README import check depends on the first clause.

**Why two projects.** The library is meant to be published and depended on;
the Worldview code is a reference implementation until a generic adapter and
MCP layer exist in `geoui`. The demo is a workspace member rather than a plain
directory because `worldview` has to be importable from four places with
different `sys.path`s: marimo (puts `demo/` on the path), FastMCP's by-path
loader (only the venv `bin/`), pytest (repo root) and `python -m` (repo root).
An editable install is the one mechanism that serves all four without shims.

## 3. The protocol (read `docs/spec.md` for the full contract)

Tiny required core + opt-in URI-identified extensions + namespaced field
prefixes + layered validation.

**Core:** `geoui_version`, `geoui_extensions`, `viewport` (`bbox` + `crs`),
`time` (`instant` *or* `{start,end}`, mutually exclusive), `layers`
(`id` + `visible` + `opacity`).

**Extensions** are declared by URI in `geoui_extensions`; the matching
`"<prefix>:<field>"` keys live as extra keys. **Declaring and using must
agree**: a `compare:*` field without `https://geoui.org/ext/compare/v1.0.0`
declared raises, and vice versa. This mismatch is the most common logged agent
error (see the frozen `errors.jsonl`). URIs are identifiers, not fetched;
`geoui.org` is not hosted.

## 4. The adapter and the round trip

- **CRS ↔ projection:** only `EPSG:4326` (geographic), `EPSG:3413` (arctic),
  `EPSG:3031` (antarctic). Anything else raises.
- **Time coercion:** the Worldview `t` param is an instant. A range on the
  root or compare time raises; ranges are only meaningful on `chart:time`.
- **Round-trip property:** `url_to_intent(intent_to_url(x))` preserves logical
  state. Parameter order may differ, a compare URL without `t1` gains one
  (side B defaults to side A's time), and 180°-crossing chart areas normalise
  to `x2 + 360`. Embed mode is opt-in on render and not part of the intent.
- **Auto-injected layers:** `build_url` always prepends a base reflectance
  layer and appends `Coastlines_15m` / `Reference_Features_15m`. They come
  back from `get_state`; ignore them when computing refinements or grading.

## 5. The tool contract and the MCP server

Three surfaces share one contract, defined in `demo/worldview/tools/__init__.py`:

| Surface | Where | Consumer |
|---|---|---|
| async functions | `worldview.tools` | anything Python |
| MCP tools `geo_ui_render_intent_tool`, `geo_ui_get_state_tool` | `worldview.mcp.server` (`worldview-mcp`) | Claude plugin, any MCP client |
| akd `BaseTool`s | `worldview.tools.akd` | the IESO agents |

`demo/worldview/tests/mcp/fixtures/akd_contract.json` is a golden capture of the
original akd-ext server (names, input schemas, descriptions, output schemas).
`demo/worldview/tests/mcp/test_server.py` asserts the standalone server matches it exactly,
except for two deliberate deltas:

1. The akd `OutputSchema` leaked an empty `_response` key into every result;
   it is gone. Nothing in the plugin or the benchmark logs read it.
2. The hosted akd server also exposed `worldview_permalink_tool`,
   `umm_vis_lookup_tool` and `earthdata_search_landing_page_tool` as a side
   effect of its global registry. This server exposes only the two protocol
   tools. The plugin has dedicated servers for the others.

**Redeploy checklist** (the hosted server still runs from the old akd-ext
branch `feature/geoui-mcp-tools`):

1. Push this repo to GitHub.
2. Create a FastMCP Cloud server from it; `fastmcp.json` names the entrypoint
   `demo/worldview/mcp/server.py:mcp`. A new deployment mints a new bearer token.
3. `MCP_BEARER_TOKEN=... uv run python scripts/dump_mcp_contract.py <new url> --only geo_ui_`
   and diff against `scripts/dump_mcp_contract.py local --only geo_ui_`.
4. Update the `geoui` server URL in
   `claude-skills-and-plugins/plugins/worldview-assistant/.mcp.json` and in
   `skills/worldview-assistant/references/tools/mcp_config.json`; refresh the
   `ieso_mcp_key` user-config description if the token changed.
5. Keep the old server until the plugin is switched.

## 6. The agents and the benchmark

`IESOWorldviewGeoUIAgent` is a `PydanticAIBaseAgent` (defaults
`openai:gpt-5.2`, `reasoning_effort="medium"`). Output is the structured
schema (`result` + `url`) or `TextOutput` for clarifying turns.

**Tooling split, deliberate:** local akd tools (`GeoUIRenderIntentTool`,
`GeoUIGetStateTool`, `UMMVisLookupTool`, `EarthdataSearchLandingPageTool`,
`SDESearchTool`; the last three were moved from hosted MCPs to local tools to
dodge cold-start flakiness); two remote MCPs (`CMR_MCP_Server`, AWS-hosted;
`IESO_Validation_MCP_Server`, FastMCP-hosted, needs `VECTOR_DB_TOOL_KEY`);
Playwright MCP added by the notebook and narrowed to `browser_navigate` +
`browser_evaluate` (the VLM agent allows eleven browser tools).

**Playwright/CDP design, the subtle part.** Chromium is launched externally
by `demo/start.sh` with `--remote-debugging-port=9222`; a fresh Playwright
MCP attaches per turn over CDP (`demo/worldview/agents/_common.py`). Holding one MCP across marimo cells hit
`RuntimeError: Attempted to exit cancel scope in a different task than it was
entered in` (anyio binds the task group to the entering task; marimo's
per-cell tasks die on return). Map state lives outside Python, in Chromium;
the MCP lives one `arun` at a time. The long docstrings in
`make_playwright_mcp` / `playwright_capability` explain this. Do not simplify
them.

**What the model sees is pinned.** `demo/worldview/tests/agents/fixtures/agent_surface.json`
is a golden of each agent's system prompt, bound config description, tool
and capability lists, browser allow-list and output-schema names, docstrings
and field descriptions. `test_agent_surface.py` fails on any drift. Change
prompts or schemas deliberately, then regenerate with
`uv run python scripts/capture_agent_surface.py` and review
the fixture diff. Output-schema and agent class names are part of that
surface: pydantic-ai names the output tool `final_result_<ClassName>` and
`agent.name` is the snake_case class name, both of which appear in the
frozen logs.

**Benchmark.** Same agent skeleton, same discovery tools, same prompts; only
the observe/act mechanism varies. Prompts are fully specified (exact layer
IDs for GeoUI, searchable names for VLM) so discovery does not dominate the
measured cost. Judging is state-field equivalence on the parsed URL,
excluding `viewport.bbox`, `chart:area` and auto-injected layers. Each turn
writes one row to `benchmarks/runs.jsonl` under the current working
directory (the repo root when launched via `demo/start.sh`); override with
`BENCHMARK_LOG_PATH` / `BENCHMARK_ERROR_LOG_PATH`. Poster figures came from
the frozen logs; the aggregation was done ad hoc and **there is still no
`benchmarks/aggregate.py`**. The VLM sample is thin (5 logged turns vs 46).

**Run:**

```bash
uv sync
cp .env.example .env                      # OPENAI_API_KEY, VECTOR_DB_TOOL_KEY
./demo/start.sh                           # treatment
AGENT=vlm ./demo/start.sh                 # baseline
uv run python -m worldview.agents.geoui_agent  # one-LLM-call wiring smoke
```

## 7. Gotchas, known issues, open TODOs

- **pydantic-ai is pinned `<2`.** akd-ext at the pinned commit imports
  `pydantic_ai.messages.BuiltinToolCallEvent`, which 2.x removed. Lift the pin
  only together with an akd-ext bump.
- **akd-ext is pinned to commit `2ca52da`** because `origin/develop` lacks
  `akd_ext/tools/worldview/` (UMM-Vis lookup, Earthdata Search). `uv sync`
  therefore needs GitHub access to `NASA-IMPACT/akd-ext`; `uv sync --no-dev`
  installs the library alone.
- **Duplicated permalink logic.** `demo/worldview/adapter/permalink.py` and
  akd-ext's `akd_ext/tools/worldview/permalink.py` are now two copies. This
  repo is the source of truth. Follow-up in akd-ext: depend on
  `geoui-protocol` plus `geoui-worldview-demo` (or whatever the adapter is
  published as), reduce its permalink module to a `BaseTool` wrapper over
  `worldview.adapter`, and drop `akd_ext/tools/geoui/`.
- **Do not move `demo/chat.py` into `demo/worldview/`.** marimo inserts the
  notebook's directory at the front of `sys.path`. Inside the package that
  directory contains `mcp/` and `agents/`, which would shadow the installed
  `mcp` SDK and `agents` packages and break pydantic-ai's imports on the first
  cell. The notebook lives beside the package, not inside it.
- **`IESO_Validation_MCP_Server` auth.** The agent flags a possible
  authorization issue. Confirm `VECTOR_DB_TOOL_KEY`; it is sent as
  `Bearer {key}` (prefix required by FastMCP servers).
- **Extension declare/use mismatch** is the top logged agent error. Since
  October 2026 the akd tool wrappers raise it as `SchemaValidationError`,
  which akd-ext turns into a pydantic-ai `ModelRetry`, so the model gets to
  add the URI and call the tool again instead of the whole turn failing
  (verified live: turn 2 of the demo shows two `geo_ui_render_intent_tool`
  calls, then success). If you touch the system prompt's extension
  instructions, re-run Workflow A turns 2/4/5.
- **marimo is pinned `<0.24`.** 0.25.x's frontend rejects its own chat
  requests (`messages[0].metadata` missing) before the handler runs.
- **Usage token counts read 0** in `runs.jsonl` rows produced with
  pydantic-ai 1.81 + gpt-5.2 (`reasoning_tokens` and `requests` are
  populated). `extract_usage` in `benchmark/log.py` needs revisiting before
  the next benchmark round; the poster numbers came from an older stack.
- **The open-ended smoke query is expensive.** "What can you help with?"
  drove 46 tool calls before the agent asked a clarifying question. The
  fully specified fast path (exact layer id + bbox + date) takes 3.
- **CMR MCP trailing slash is load-bearing**: without it the server 307s and
  pydantic-ai's streamable-HTTP client raises instead of following.
- **Chart `time` must be a range**; root/compare `time` must be an instant.
- **Workflow C** needs the chlorophyll GIBS layer id looked up before it runs.
- **Benchmark log default path changed** from "worktree root derived from the
  module's location" to `Path.cwd()/benchmarks/`. Always launch from the repo
  root, or set the env overrides.
- **Not in this repo:** the `ieso-worldview-plugin/` directory from the old
  worktree (the live copy is `claude-skills-and-plugins/plugins/worldview-assistant`),
  the old `ieso_w_geoui` shim modules, Playwright console logs, and the
  partial `benchmarks/backup` duplicate.

## 8. Orientation checklist for the next person

1. Read `docs/spec.md`, then §3–§5 here.
2. `uv sync && uv run pytest`: 140-odd tests, no keys, no network except the
   stdio smoke spawning a subprocess.
3. `uv run worldview-mcp --transport http --port 8000` and
   `uv run python scripts/dump_mcp_contract.py http://127.0.0.1:8000/mcp`.
4. Fill `.env`, `./demo/start.sh`, try *"Show
   aerosol optical depth over California on 2025-09-15"*, then *"compare it
   to the previous day"*.
5. Pick up §7 and the README roadmap: aggregation script, more VLM runs,
   conformance harness.
