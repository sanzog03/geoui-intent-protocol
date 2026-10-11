# GeoUI Intent Protocol — Handover

> A short reference doc for **forking this work** into a new
> adapter project (e.g. Cesium, QGIS, Leaflet, Mapbox). Read
> top to bottom once; come back to §4 and §5 when you're
> actually building.

## What this is

The **GeoUI Intent Protocol** lets an LLM agent drive a
geospatial visualization through a **typed declarative
intent** — viewport, time, layers — instead of through
screenshots + DOM + clicks. On iterative NASA Worldview
workflows (n = 4), the protocol path is **~15× cheaper per
task** than a VLM + browser-control baseline, and **answers
correctly** on questions where the baseline cannot (geo
viewers render through canvas + WebGL, which the DOM does not
expose; semantic map state is not recoverable from pixels).

**Authors:** Sanjog Thapa (lead, NASA ODSI / UAH,
`sanjog.thapa@uah.edu`), Kumar, Nish, Rohit, Iksha, Rahul.
**Venue:** 2nd ESA-NASA International Workshop on AI Foundation
Models for Earth Observation, NASA MSFC, May 2026.

---

## Where everything lives

Everything now lives in one repository, `geoui_intent_protocol`
(Python package `geoui`, distribution `geoui-protocol`). The original
implementation was developed inside an `akd-ext` worktree and extracted
in October 2026; this document is kept as the poster-era narrative.

| Concept | Path (relative to the repo root) |
|---|---|
| Protocol spec (canonical) | `docs/spec.md` |
| `GeoIntent` core schema | `geoui/core.py` |
| Extensions (compare / chart / raster-styling) | `geoui/extensions/{compare,chart,raster_styling}.py` |
| Reference adapter (Worldview) | `geoui/adapters/worldview/` |
| Tool surface (`render_intent`, `get_state`) | `geoui/tools.py` |
| MCP server | `geoui/mcp/server.py` (`geoui-mcp`) |
| Agent — GeoUI variant | `geoui/agents/geoui_agent.py` |
| Agent — VLM baseline variant | `geoui/agents/vlm_agent.py` |
| Benchmark prompt suite | `benchmarks/prompts.md` |
| Benchmark turn-level logs (frozen) | `benchmarks/results/poster-2026-05/{runs,errors}.jsonl` |
| Demo entrypoint (chromium + marimo) | `demo/start.sh` (`AGENT=geoui|vlm`) |
| Poster narrative | `docs/poster/poster-slots.md`, `docs/poster/poster-draft.md` |
| Benchmark chart | `docs/poster/figs/results_chart.png` |

## Protocol overview

The protocol is **a tiny core + URI-identified extensions**, in
the spirit of STAC.

**Core fields of `GeoIntent`**

- `viewport` — bbox + CRS (`EPSG:4326`, `EPSG:3413`,
  `EPSG:3031`, …)
- `time` — `instant` or `{start, end}`
- `layers` — ordered list of `LayerRef` (`id`, `visible`,
  `opacity`)
- `geoui_extensions` — list of extension URIs declared by this
  intent

**Two MCP tools at the adapter boundary**

- `render_intent(intent: GeoIntent) -> handle` — apply the
  agent's intent to the application
- `get_state() -> GeoIntent` — return the application's
  current state in the same shape

The agent **only ever** reads and writes `GeoIntent`. Anything
application-specific (URL formats, RPC schemas, DOM, pixels)
lives strictly inside the adapter.

**Extensions** are namespaced and declared per intent. Reference
set:

- `ext/compare/v1.0.0` — A/B layer comparison
- `ext/chart/v1.0.0` — time-series statistics over a region
- `ext/raster-styling/v1.0.0` — per-layer palettes,
  min/max, squash

Each extension is a Pydantic model plus translator logic in the
adapter. Field names are namespaced (`compare:mode`,
`chart:area`, …) so the core stays small and conflict-free.

**Adapter responsibility:** translate `GeoIntent` ↔ the
application's native state. **The geo-visualization application
itself is not modified.** Worldview, for instance, is wrapped
by mapping `GeoIntent` to Worldview's existing
`WorldviewPermalinkInputSchema` and back.

> For the canonical, versioned spec, see `docs/spec.md`.

---

## Forking a new adapter

The recipe below mirrors the Worldview reference implementation.
A reader with `geoui/adapters/worldview/adapter.py` and
`geoui/tools.py` open can follow it end-to-end.

1. **Pick the target application.** Confirm it has a stable
   representation of its current state you can both **write**
   (to drive the view) and **read** (to recover state after
   user interaction). Examples:
   - Worldview → permalink URL
   - Cesium → a `Viewer` config object via the JS bridge
   - QGIS → project XML or PyQGIS API
   - Leaflet / Mapbox → JS map state queried via Playwright

2. **Pick your supported subset.** Start with `viewport`,
   `time`, and `layers` only. Defer extensions until the core
   round-trips cleanly. Premature extension support is the
   single most common way these adapters fall over.

3. **Write the translators.** Mirror
   `geoui/adapters/worldview/adapter.py`:
   ```python
   def intent_to_<native>(intent: GeoIntent) -> NativeState: ...
   def <native>_to_intent(state: NativeState) -> GeoIntent: ...
   ```
   Aim for the **round-trip property**:
   `intent → native → intent` is the identity function on the
   supported subset of fields. If it isn't, the agent will see
   spurious "state drift" after every `render_intent` call.

4. **Wrap as MCP tools.** Mirror `geoui/tools.py` (and `geoui/mcp/server.py`):
   - `RenderIntentTool` — applies `intent_to_<native>` and
     drives the app
   - `GetStateTool` — queries the app, returns
     `<native>_to_intent(...)`

   Both as `BaseTool` subclasses. Keep their schemas the same
   shape as the GeoUI tools so logs and benchmarks stay
   comparable.

5. **Wire into an agent.** Mirror `geoui/agents/geoui_agent.py`:
   factory function returning
   `[YourRenderIntentTool, YourGetStateTool,
   …shared discovery tools]`. The GeoUI agent system prompt is
   app-agnostic at the protocol layer — **reuse it verbatim**
   where you can, and only patch the parts that name Worldview
   specifically.

6. **Add extensions only when you need them.** Each extension
   is a Pydantic model in `extensions/<name>.py` plus
   translator logic in the adapter. Declared per intent via
   `geoui_extensions: ["ext/<name>/vX.Y.Z"]`. If the target
   app can't express the extension, declare and document the
   gap — don't silently drop fields.

### Conformance checklist

A fork is "GeoUI-protocol-conformant" when:

- [ ] **Round-trip:** `intent → native → intent` is the
      identity on supported fields
- [ ] `get_state()` is **read-only** (no side effects)
- [ ] `render_intent()` is **idempotent** for the same intent
- [ ] Declared `geoui_extensions` match what the adapter
      actually handles
- [ ] All `LayerRef.id`s validate against the app's layer
      registry (or document where the lookup boundary lives)

---

## Reproducing the benchmark

The benchmark exists to make a single claim **per adapter**:
"protocol path beats VLM-baseline path by ~N× on cost, and is
correct on tasks the baseline gets wrong."

### Setup parity

Run the same agent skeleton against the same prompt suite,
varying only the **interaction mechanism**:

- **GeoUI variant** — uses your `RenderIntentTool` /
  `GetStateTool`
- **VLM variant** — uses Playwright MCP directly: screenshot,
  accessibility snapshot, click, type, drag

**Hold discovery tools equal** across the two variants (CMR,
vector-DB, Earthdata-search, or whatever the app's domain
catalog is). Both system prompts must include a
**fully-specified-intent fast-path** that skips the discovery
loop when the user provides exact IDs — this is what isolates
the comparison to the interaction mechanism rather than the
discovery loop.

### Prompt suite

Use `benchmarks/prompts.md` as the template. Each prompt is
authored in two forms:

- **GeoUI** gets the **exact registry ID**
  (e.g. `MODIS_Aqua_Aerosol_Optical_Depth_3km`)
- **VLM** gets the **verbose searchable name**
  (e.g. *"MODIS Aqua Aerosol Optical Depth 3km"*)

Each side gets the input it can consume directly.

### Workflow axes (keep these; swap the IDs)

Single-layer render · date refinement · spatial pan · A/B
compare · time-series chart · multi-layer overlay. These are
the axes the Worldview suite covers, and they generalize.

### Run

```bash
./demo/start.sh             # treatment (GeoUI)
AGENT=vlm ./demo/start.sh   # baseline (VLM + browser control)
```

Each launches chromium + a marimo notebook with the relevant
agent. Run each prompt in both variants. Turn-level
pydantic-ai output lands in `benchmarks/runs.jsonl`; errors in
`benchmarks/errors.jsonl`.

### Metrics per task

Input tokens, output tokens, total tokens, LLM round-trips,
tool calls, reasoning tokens, cache-read tokens, wall clock.
Plus a **qualitative accuracy log**: after a manual pan, ask
*"what region am I viewing?"* — does `get_state()` answer
correctly? Does the VLM variant?

### Aggregation

**There is no checked-in aggregation script yet.** Poster
numbers were computed ad-hoc from `runs.jsonl`. **Strongly
recommended for any fork:** add a small reusable aggregator
(e.g. `benchmarks/aggregate.py`) that averages metrics across
N workflows and emits the same ratio table the poster shows.
Same chart shape → results comparable across adapters.

---

## Known gaps / opportunities

- **n = 4** hand-curated workflows. Pushing n is the obvious
  next move.
- **Accuracy is qualitative.** One worked example ("what region
  am I viewing?") is described in the poster; a logged Q&A
  appendix per fork would harden the claim.
- **No aggregation script.** Each fork should standardize one
  (see §5).
- **Generic protocol diagram is still ASCII.** Source lives in
  `geoui-protocol-generic-interaction.md` (referenced in
  `poster-slots.md` §5A); needs vector rework before any
  external publication.
- **Browser control is outside the protocol today.** Playwright
  navigates to the URL `render_intent()` returns. A future
  protocol revision could pull browser control inside the
  protocol so the adapter, not the agent, owns it.
- **Token-cost figures depend on model + prompt-cache pricing.**
  Re-derive when forking onto a new model.

---

## Citing this work

> Thapa, S., Kumar, Nish, Rohit, Iksha, Rahul.
> **GeoUI Intent Protocol — Token Efficiency and Accuracy for
> Agentic Geospatial Visualization.** 2nd ESA-NASA International
> Workshop on AI Foundation Models for Earth Observation,
> NASA MSFC, May 2026. Contact: `sanjog.thapa@uah.edu`.
