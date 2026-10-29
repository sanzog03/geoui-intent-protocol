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
adapter, the two tools (plain functions, an MCP server, and a pydantic-ai toolset), the
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
| `demo/worldview/tools/__init__.py` | The three operations as async functions (render, get-state, `geo_ui_list_intent_extensions_tool`), request/response models, the agent-facing docstrings, and `prepare_intent` (pre-declares the adapter's `SUPPORTED_EXTENSIONS` on every intent, refuses other namespaces). The intent field description and the catalogue are generated from that list. Single source of truth for all three tool surfaces. | adapter |
| `demo/worldview/mcp/_describe.py` | Rebuilds akd's `INPUT/OUTPUT FIELD DESCRIPTIONS` description suffix so the MCP contract matches the original deployment. | — |
| `demo/worldview/mcp/server.py` | `FastMCP("geoui")` with the three tools; `main()` is the `worldview-mcp` CLI. Absolute `worldview.*` imports only: FastMCP loads this file standalone. | fastmcp |
| `demo/worldview/tools/pai.py` | pydantic-ai toolsets: `geoui_toolset` (the three protocol tools, same names/descriptions as the MCP server, real parameter descriptions) and `permalink_toolset` (`worldview_permalink_tool` over `build_url`). Protocol `ValueError`s become `ModelRetry` so the model gets a retry. | pydantic-ai |
| `demo/worldview/plugin.py` | Claude Code plugin loader: `load_skill` (SKILL.md body = system prompt, frontmatter stripped), `reference_toolset` (`list_references` / `read_reference` over the skill's `references/`), `load_mcp_config` (`.mcp.json` → pydantic-ai MCP servers, `${user_config.*}` filled from env, keyless servers dropped with a warning), `remote_capabilities`, `playwright_server` (`--cdp-endpoint` appended). | pydantic-ai |
| `demo/worldview/agents/_common.py` | `AgentSpec` + `build_agent` (bare `pydantic_ai.Agent`, output type `[<Structured>, TextOutput]`, output validator for empty result/url), `standard_capabilities` (remote MCPs + narrowed Playwright + `Thinking(effort="medium")`), the two browser allow-lists, `TextOutput`, `run_smoke`. The Playwright/CDP design note lives here. | pydantic-ai, `plugin` |
| `demo/worldview/agents/geoui_agent.py` | `geoui_spec` / `build_geoui_agent` (treatment): the `worldview-assistant` skill as system prompt, `geoui_toolset` + `permalink_toolset` + references, `GEOUI_BROWSER_TOOLS`, `GeoUIAgentOutput`. | `_common` |
| `demo/worldview/agents/vlm_agent.py` | `vlm_spec` / `build_vlm_agent` (baseline): the vendored `mio-worldviewagent-v2` skill plus `VLM_BROWSER_ADDENDUM` as a second prompt part, `permalink_toolset` + references (no GeoUI tools), `VLM_BROWSER_TOOLS`, `VLMAgentOutput`. | `_common` |
| `demo/worldview/agents/warm_mcps.py` | Pings each enabled remote MCP once at launch to absorb FastMCP cold starts. | httpx |
| `demo/worldview/agents/artifact/worldview/geoui/akd-plugins/` | git submodule of `NASA-IMPACT/akd-plugins`; `plugins/worldview-assistant/` holds `.mcp.json`, `.claude-plugin/plugin.json` (declares the `userConfig` keys) and `skills/worldview-assistant/`. | — |
| `demo/worldview/agents/artifact/worldview/vlm/mio-worldviewagent-v2/` | Vendored non-GeoUI skill (`SKILL.md` + `references/`, see its README for provenance). | — |
| `demo/worldview/agents/benchmark/log.py` | Per-turn JSONL logging (`TurnRecord`, `ErrorRecord`, `append_*`, `load_runs`). | pydantic |
| `demo/chromium.sh` | Chromium-over-CDP helpers (`ensure_chromium` launches or reattaches on port 9222 and exports `PLAYWRIGHT_CDP_ENDPOINT`), sourced by `demo/start.sh` and by `WorldviewApp.prepare()` in `benchmarks/worldview/app.py`. | curl, npx |
| `demo/start.sh` | Sources `chromium.sh`, warms MCPs, opens the marimo notebook. `AGENT=geoui` (default) or `vlm`. | uv, npx |
| `demo/chat.py` | One marimo multi-turn chat app for both agents; `AGENT=geoui` (default) or `vlm` picks the factory, intro text, example prompts and benchmark-log label. Carries pydantic-ai `message_history` across turns; attaches Playwright per turn via CDP. | marimo |
| `benchmarks/geouibench/` | **The benchmark utility, mechanism-neutral; names no application.** `app.py` (`BenchmarkApp` protocol, `UIState`, `prepare_app`), `appdir.py` (app directories: load `app.py` by path, resolve datasets by name), `state.py` (expected vs observed UI state), `datasets.py` (goldens + metadata, per-agent openers, dataset hash), `records.py` (TurnRecord/ErrorRecord rows), `tracing.py` (deepeval pydantic-ai instrumentation as a capability, `traced_turn`, `TurnTrace`), `harness.py` (`ConversationRunner.respond`, the simulator callback; CDP tab reset; transcripts), `metrics.py` (the six metrics + `state_reached_controller`), `runner.py` (`run_golden`: simulate → assert_test → record; `ensure_run_info`), `evals/test_benchmark.py` (the one deepeval suite, driven by `BENCHMARK_APP`), `synthetic.py` (`SyntheticStyle`, `generate` around `deepeval generate`), `score.py` (offline re-score from traces), `summary.py` / `summarize.py` (rows, ratios, totals, markdown), `run_dir.py` (run.json, path scrubbing), `cli.py` (`python -m geouibench run\|score\|summarize\|synthetic\|datasets`). Tests under `geouibench/tests/` with a `FakeApp` on `TestModel` and a stand-in simulator. | deepeval, pydantic-ai |
| `benchmarks/worldview/` | **The Worldview app directory** (no package, no pyproject). `app.py` (`APP = WorldviewApp()`: both factories, `observe(url)`, discovery tools, roles, `DEFAULT_BUDGETS`, `prepare()` = plugin check + `demo/chromium.sh` + MCP warm-up, `SYNTHETIC_STYLE`), `datasets/gold_dataset.json` (Core 1–6 + workflows A/B with openers, expected state, checkpoints), `datasets/synthetic_queries.json`, `tests/`, `results/<run-id>/` (committed runs). | geouibench, demo |
| `benchmarks/worldview_legacy/prompts.md`, `benchmarks/worldview_legacy/workflows.md` | Prompt suite (Core 6 + Optional 4) and 5-turn scenario scripts (A: CA wildfire smoke; B: Saharan dust; C: Lake Erie bloom). | — |
| `benchmarks/worldview_legacy/results/poster-2026-05/` | Frozen `runs.jsonl` (51 rows) and `errors.jsonl` (22 rows) behind the poster. Absolute paths in tracebacks were replaced (`<worktree>` for the source checkout, `<python>` for the interpreter install). | — |
| `scripts/dump_mcp_contract.py` | Dump any server's tool contract as JSON. | fastmcp |
| `demo/pyproject.toml` | The `geoui-worldview-demo` project: a uv workspace member that depends on `geoui-protocol` and owns the heavy dependencies (pydantic-ai, fastmcp, marimo). The root dev group installs it editable. | — |
| `benchmarks/pyproject.toml` | The third workspace member, `geouibench` (owns deepeval). The root dev group installs it editable; the demo never depends on it. App directories under `benchmarks/` are not members. | — |
| `tests/` | `test_core.py` and `test_benchmark_results.py` (library and repo-level; the latter scans every committed benchmark artifact for absolute paths). | — |
| `demo/worldview/tests/` | `adapter/` (permalink, assembly, round trip); `mcp/test_server.py` (contract vs golden, calls, stdio smoke); `agents/test_plugin.py` (loader), `agents/test_pai_tools.py` (toolset parity) and `agents/test_agent_surface.py` (model-visible surface golden, plus a no-akd check). Collected by the root `pytest` via `testpaths`. | — |

**Layering rule:** `geoui` imports only pydantic and never `worldview`.
`worldview.adapter` adds dateutil; `worldview.tools` the adapter;
`worldview.mcp` fastmcp; `worldview.tools.pai`, `worldview.plugin` and
`worldview.agents` pydantic-ai. The benchmark sits on top: `geoui` ←
`geouibench` ← `benchmarks/worldview/app.py` → `worldview`; `geouibench` never
imports or names `worldview`, and `demo/` never imports `geouibench` or
deepeval. Nothing imports akd. The README import check depends on the first
clause.

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
| pydantic-ai toolset | `worldview.tools.pai` | the demo agents |

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

Both agents are bare `pydantic_ai.Agent`s (`openai:gpt-5.2`,
`Thinking(effort="medium")`, `retries=1`) built by `build_agent(AgentSpec)`.
Output is the structured class (`result` + `url`) or `TextOutput` for
clarifying turns, so the output tools are `final_result_GeoUIAgentOutput` /
`final_result_VLMAgentOutput` and `final_result_TextOutput`.

**Prompts come from Claude Code skills.** The GeoUI agent's only system
prompt is `skills/worldview-assistant/SKILL.md` from the plugin submodule
(frontmatter stripped). The baseline runs the vendored
`mio-worldviewagent-v2/SKILL.md`, which knows nothing about GeoUI and builds
URLs with `worldview_permalink_tool`, plus `VLM_BROWSER_ADDENDUM` (the
observe/act and turn-gate rules from the poster-era prompt). Each skill's
`references/` tree is reachable through `list_references` / `read_reference`;
nothing under `references/` is injected up front, and `assets/` (the catalog
and story mirrors) is not exposed.

**Tooling split, deliberate:** in-process `geoui_toolset` (the two protocol
tools) and `permalink_toolset`; every discovery tool is a remote MCP taken
from the plugin's `.mcp.json` (`cmr`, `ieso-validation`, `umm-vis-lookup`,
`earthdata-search`, `pdf-parser`, `sde-search`, `eonet`), the plugin's
`geoui` and `worldview-permalink` entries being replaced by the local
toolsets. Secrets are `${user_config.*}` placeholders filled from
`VECTOR_DB_TOOL_KEY`, `IESO_MCP_KEY`, `SDE_MCP_KEY`, `EONET_TOKEN`; a server
whose key is unset is dropped with a `worldview.plugin` warning, so the agent
simply has fewer tools. Playwright comes from the same config, gets
`--cdp-endpoint` appended, and is narrowed to `browser_navigate` +
`browser_evaluate` for GeoUI and to eleven tools for the baseline.

**Playwright/CDP design, the subtle part.** Chromium is launched externally
by `demo/start.sh` with `--remote-debugging-port=9222`; a fresh Playwright
MCP attaches per turn over CDP (`demo/worldview/agents/_common.py`). Holding one MCP across marimo cells hit
`RuntimeError: Attempted to exit cancel scope in a different task than it was
entered in` (anyio binds the task group to the entering task; marimo's
per-cell tasks die on return). Map state lives outside Python, in Chromium;
the MCP lives one run at a time. The design note in `_common.py` explains
this. Do not simplify it.

**What the model sees is pinned.** `demo/worldview/tests/agents/fixtures/agent_surface.json`
is a golden of each agent's system prompts, in-process tool names /
descriptions / parameter schemas, capability list (remote MCP ids and URLs,
Playwright allow-list, reasoning effort), output tool names and output
schemas. `test_agent_surface.py` fails on any drift, including a plugin
submodule bump or a re-exported skill. Change things deliberately, then
regenerate with `uv run python scripts/capture_agent_surface.py` and review
the fixture diff. Output class names are part of that surface: pydantic-ai
names the output tool `final_result_<ClassName>`, and the name appears in the
benchmark logs. Logs written before October 28, 2026 carry the old names
(`final_result_IESOWorldview*OutputSchema`, agents `ieso_worldview_*`).

**Benchmark (deepeval, since October 28, 2026).** `python -m geouibench run
benchmarks/worldview gold` runs both agents on the same goldens and scores
them with the same six metrics; `benchmarks/worldview/README.md` is the
operating manual and `benchmarks/README.md` the design (including how to
benchmark another demo: a new app directory with an `app.py` and a gold
dataset, nothing else). The shape: deepeval's
`ConversationSimulator` (gpt-5.2) plays the user, answering each gold
scenario's verbatim opener (layer-id wording for geoui, searchable-name
wording for vlm, as `prompts.md` does on purpose) and improvising the listed
follow-up steps; `geouibench.harness.ConversationRunner.respond` runs each turn
under deepeval's pydantic-ai instrumentation (passed through the factories'
`extra_capabilities`, so the agents are untouched) and saves one `TurnTrace`
per turn; `state_reached_controller` stops a conversation when the final URL
satisfies the golden's `expected_state` and every checkpoint, or at the
golden's extra-turn cap. Metrics: **Success** (final URL → UI state vs
expected, bbox excluded), **Completion** (checkpoints + deepeval
`ConversationCompletenessMetric`), **Tool / Time / Token efficiency**
(deterministic, from the traces, against per-scenario budgets identical for
both agents), **Turn relevancy** (deepeval). `python -m geouibench score <run>`
recomputes the deterministic four from the committed traces without an agent;
`summary.md` has the VLM ÷ GeoUI ratios. The notebook procedure, its prompt
suite and the frozen poster logs stayed under `benchmarks/worldview_legacy/`; the
notebook still logs there and knows nothing about deepeval.

**Run:**

```bash
git submodule update --init               # once: the worldview-assistant plugin
uv sync
cp .env.example .env                      # OPENAI_API_KEY, then the MCP keys you have
./demo/start.sh                           # treatment
AGENT=vlm ./demo/start.sh                 # baseline
uv run python -m worldview.agents.geoui_agent  # one-LLM-call wiring smoke
uv run python -m geouibench run benchmarks/worldview gold --smoke --run-id smoke   # benchmark: one scenario, both agents
uv run python -m geouibench run benchmarks/worldview gold --run-id 2026-10-28-gold # benchmark: the gold set (~15 min geoui, 1.5–2.5 h vlm)
uv run python -m worldview.agents.warm_mcps    # lists the enabled remote servers
```

## 7. Gotchas, known issues, open TODOs

- **pydantic-ai is pinned `>=2.63,<3`** (since October 28, 2026). MCP servers
  are `MCPToolset`s over fastmcp transports (`worldview.plugin.transport_of`),
  `result.usage` is a property, `RunUsage.output_reasoning_tokens` is a
  top-level field, and the model string stays `openai-chat:` so the 2.x
  Responses-API default does not change behaviour silently.
- **No akd anywhere** since October 28, 2026. The agents are bare pydantic-ai;
  `test_no_akd_anywhere` fails if an import creeps back. The MCP contract
  golden is still called `akd_contract.json` because it was captured from the
  original akd-ext server.
- **The plugin is a git submodule.** A fresh clone without
  `--recurse-submodules` has an empty `agents/artifact/worldview/geoui/akd-plugins`; `start.sh`
  and `worldview.plugin.plugin_dir()` say so. `WORLDVIEW_PLUGIN_DIR` points at
  any other checkout of the plugin.
- **Missing MCP keys shrink the tool set silently (well, with a warning).**
  `load_mcp_config` drops every server whose `${user_config.*}` is unset. The
  env cell lists the disabled groups; the skill then falls back to the
  remaining tools or asks the user. The local copy of the plugin under
  `claude-skills-and-plugins` holds literal tokens: never vendor it.
- **Duplicated permalink logic.** `demo/worldview/adapter/permalink.py` and
  akd-ext's `akd_ext/tools/worldview/permalink.py` are two copies. This repo
  is the source of truth. Follow-up in akd-ext: depend on `geoui-protocol`
  (plus the adapter once it is published), reduce its permalink module to a
  wrapper over `worldview.adapter`, and drop `akd_ext/tools/geoui/`.
- **Do not move `demo/chat.py` into `demo/worldview/`.** marimo inserts the
  notebook's directory at the front of `sys.path`. Inside the package that
  directory contains `mcp/` and `agents/`, which would shadow the installed
  `mcp` SDK and `agents` packages and break pydantic-ai's imports on the first
  cell. The notebook lives beside the package, not inside it.
- **`IESO_Validation_MCP_Server` auth.** The agent flags a possible
  authorization issue. Confirm `VECTOR_DB_TOOL_KEY`; it is sent as
  `Bearer {key}` (prefix required by FastMCP servers).
- **Extension declare/use mismatch** is the top logged agent error. The
  in-process toolset raises it as a pydantic-ai `ModelRetry`, so the model
  gets to add the URI and call the tool again instead of the whole turn
  failing (verified live: turn 2 of the demo shows two
  `geo_ui_render_intent_tool` calls, then success). The skill's step 6 spells
  out the declare-and-populate rule; if the plugin changes it, re-run
  Workflow A turns 2/4/5.
- **MCP tools carry their own retry budget.** pydantic-ai's agent-level
  `retries` never reaches MCP tools; each server has `max_retries` (default
  1). The VLM baseline's Playwright server gets `max_retries=3` and
  `--timeout-action 15000` because Worldview's first-visit tour overlay made
  a `browser_click` time out twice and abort the turn. The GeoUI agent never
  clicks and keeps 1.
- **The VLM baseline has no URL builder.** With `worldview_permalink_tool`
  wired next to full browser control, the skill's step 6 ("call the permalink
  tool") and the addendum ("only the UI changes state") pulled the model both
  ways and it looped on the tool until the 50-request cap. The addendum now
  states it overrides step 6; the baseline's only local tools are the skill
  references. A clean baseline turn took 26 tool calls and 6.3 minutes, versus
  4 calls and 21 s for the GeoUI agent on the same request.
- **marimo is pinned `<0.24`.** 0.25.x's frontend rejects its own chat
  requests (`messages[0].metadata` missing) before the handler runs.
- **Usage token counts read 0** in every manual `runs.jsonl` row written on
  pydantic-ai 1.81 (`reasoning_tokens` and `requests` were populated): 1.81
  accepted any `genai-prices`, 0.1.x added `output_reasoning_tokens`, and
  1.81's `RequestUsage.extract` swallowed the resulting `TypeError`. Gone
  since 1.107; rows before October 28, 2026 are not token-comparable.
- **deepeval gotchas (benchmark).** Its pytest plugin auto-registers into
  every pytest run; the root `addopts` carries `-p no:deepeval`, which
  `deepeval test run` re-enables. It only writes result JSON when launched by
  its CLI (`DEEPEVAL_RESULTS_FOLDER`). `ConversationSimulator` detects async
  callbacks with `inspect.iscoroutinefunction`, so pass the bound method
  `runner.respond`, never the runner instance. It re-instantiates metrics per
  test case with every attribute whose name is an `__init__` parameter in the
  MRO, so custom metric constructors must accept `threshold` and the
  attributes they store. `max_user_simulations` must be > 0; single-shot
  goldens rely on `state_reached_controller` to stop after the opener. Never
  run the eval suite with `-n`: both agents share one Chromium tab. deepeval's
  LLM spans carry input/output tokens but not cache-read or reasoning tokens
  (taken from `result.usage`); MCP tool calls appear twice in a trace and
  `tools/list` calls appear as untyped spans (filtered in `geouibench.tracing`).
  deepeval's `Observer` never clears `current_trace_context`, so consecutive
  `@observe` calls on one event loop nest under the first trace and every
  later turn's trace accumulates the earlier spans; `traced_turn` clears the
  context variables around each turn (`reset_trace_context`).
  `deepeval generate --method docs` needs chromadb (not installed) and
  `--method goldens` / `scratch` emit one-line scenarios with no expected
  outcome; the synthetic set was made with `--method contexts` from the gold
  scenarios (`geouibench.synthetic`, wording from the app's `SYNTHETIC_STYLE`).
  An errored turn (UsageLimitExceeded, tool retries exhausted) has no
  RunUsage, so its tokens come from the LLM spans with no cache-read credit:
  its cache-adjusted token count is an upper bound. The live eval file
  (`benchmarks/geouibench/evals/test_benchmark.py`) is outside `testpaths` and
  skips itself unless BENCHMARK_APP and BENCHMARK_RUN are set; two runs must
  never share the Chromium tab.
- **Extensions are pre-declared by the tools (since October 28, 2026).**
  Before, the model had to list an extension's URI in `geoui_extensions`
  *and* fill its `compare:*` / `chart:*` / `raster-styling:*` fields; it
  forgot the URI on the first attempt in four of eight gold conversations
  (one retry each) and the poster-era akd tools aborted the turn on it. Now
  `worldview.adapter.SUPPORTED_EXTENSIONS` is the one list: the tool layer
  pre-declares those URIs on every intent, refuses other namespaces, and
  generates the intent description and `geo_ui_list_intent_extensions_tool`
  from it (drop an entry to withdraw a capability). `geoui.extensions` treats
  a declared-but-unused extension as valid (`extract` returns None), so
  pre-declaration is protocol-conforming (`docs/spec.md`, Extension
  mechanics). Two goldens changed deliberately: the MCP contract fixture
  (regenerate with `scripts/dump_mcp_contract.py local --update-golden`)
  and the agent surface. The hosted akd-ext server no longer matches the
  contract; it was due to be replaced anyway (§5). **Skill follow-up in
  akd-plugins:** `SKILL.md` and
  `references/tools/geo_ui_render_intent_tool/index.md` still say
  "declare the URI AND fill the fields" and that undeclared fields are
  rejected; replace with "call `geo_ui_list_intent_extensions_tool` to see
  the supported extensions, then fill only their namespaced fields; never
  write `geoui_extensions`". Runs before this change are not
  token-comparable on compare / chart scenarios (one fewer LLM request).
- **Playwright MCP is `@playwright/mcp@latest`** in the plugin's `.mcp.json`;
  `run.json` does not pin it. Pin it in the plugin if runs must be
  byte-for-byte reproducible.
- **The open-ended smoke query is expensive.** "What can you help with?"
  drove 46 tool calls before the agent asked a clarifying question. The
  fully specified fast path (exact layer id + bbox + date) takes 3.
- **CMR MCP trailing slash is load-bearing**: without it the server 307s and
  pydantic-ai's streamable-HTTP client raises instead of following.
- **Chart `time` must be a range**; root/compare `time` must be an instant.
- **Workflow C** needs the chlorophyll GIBS layer id looked up before it runs.
- **Benchmark log default path changed** from "worktree root derived from the
  module's location" to `Path.cwd()/benchmarks/worldview_legacy/`. Always launch from the repo
  root, or set the env overrides.
- **Not in this repo:** the old `ieso_w_geoui` shim modules, the
  poster-era prompts that lived in `geoui_agent.py` / `vlm_agent.py` (git
  history before October 28, 2026), Playwright console logs, and the partial
  `benchmarks/backup` duplicate.

## 8. Orientation checklist for the next person

1. Read `docs/spec.md`, then §3–§5 here.
2. `git submodule update --init && uv sync && uv run pytest`: 250-odd tests
   across the four workspace projects, no keys, no network except the stdio
   smoke spawning a subprocess.
3. `uv run worldview-mcp --transport http --port 8000` and
   `uv run python scripts/dump_mcp_contract.py http://127.0.0.1:8000/mcp`.
4. Fill `.env`, `./demo/start.sh`, try *"Show
   aerosol optical depth over California on 2025-09-15"*, then *"compare it
   to the previous day"*.
5. `uv run python -m geouibench run benchmarks/worldview gold --smoke --run-id smoke`,
   read `benchmarks/worldview/results/smoke/summary.md`, then re-score it with
   `uv run python -m geouibench score benchmarks/worldview/results/smoke`.
6. Pick up §7 and the README roadmap: more scenarios and runs, the
   conformance harness.
