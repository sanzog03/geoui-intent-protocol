# Poster draft — Agentic UI for GeoAI

> Workshop: **2nd ESA-NASA International Workshop on AI Foundation Models
> for Earth Observation**, NASA MSFC, Huntsville, AL · 19–22 May 2026
>
> First-pass narrative draft. Medium-agnostic markdown — once content
> lands, port to LaTeX (`beamerposter` / `baposter` / `tikzposter`),
> Inkscape, typst, or whichever tool you'd like to lay out.
>
> Section sizing in this draft is approximately the body-text length
> each panel should hold on the final poster. Bracketed `[FIG: …]`
> markers identify visuals to render or embed.

---

## Title block

**Agentic UI for GeoAI: An Intent-Driven Framework for Iterative Geospatial Analysis**

*Authors — TODO* · The University of Alabama in Huntsville (?) · contact: `st0128@uah.edu`

*Workshop logo (ESA + NASA), institutional logo(s), workshop ID / poster number.*

---

## 1. TL;DR (the hook)

**The problem:** LLM agents that drive geospatial visualizations
either learn the app's UI (expensive, brittle, app-specific) or
emit a structured intent that the app renders (cheap, portable —
*if* a protocol exists).

**Our contribution:** the **GeoUI Protocol** — a declarative
geospatial-intent schema (STAC-inspired core + namespaced
extensions) and a thin adapter pattern that lets any geospatial
application expose itself to agents through one bounded contract.

**Empirical result:** on iterative NASA Worldview workflows, a
protocol-based agent costs **~5× fewer effective tokens and
~10× fewer tool calls per work turn** than a vision+DOM baseline
that drives the same UI manually. **One order of magnitude per
turn, compounding across iterations.**

`[FIG: hero chart — log-scale bar chart of GeoUI vs VLM costs across the 6 metrics. Use today's averaged numbers.]`

---

## 2. Motivation

Earth-science workflows are *iterative*. A researcher rarely
asks for one fixed visualization — they refine: change the date,
pan to a region, swap a layer, overlay a chart. Each refinement
is a small intent change.

When an agent drives this loop, **how the agent talks to the
visualization application becomes the dominant cost.** Two
realistic shapes:

- **VLM-baseline path** — the agent observes the page via
  screenshot + accessibility-tree snapshot and acts by clicking,
  typing, dragging. Robust to any web app, but every action
  ships a fresh page snapshot back into the model context. Token
  cost scales with UI complexity and turn count.
- **Protocol path** — the agent reasons in a typed *intent* that
  the application is responsible for rendering. The application
  also reports its current state back as the same intent shape.
  No DOM, no screenshots — just bounded, validated structure.

`[FIG: pair of side-by-side architecture diagrams — left "VLM baseline" (browser snapshot path), right "GeoUI Protocol" (intent through adapter path). Adapted from the existing ASCII docs.]`

---

## 3. The GeoUI Protocol

A declarative *Geospatial Intent Schema*, STAC-style: a small
**core** + namespaced **extensions** declared per intent. Two
MCP tools form the application-side contract.

**Core fields**

- `viewport` — bbox + CRS (`EPSG:4326`, `EPSG:3413`, `EPSG:3031`, …)
- `time` — `instant` or `{start, end}`
- `layers` — ordered list of `LayerRef` (id, visible, opacity)
- `geoui_extensions` — declared URI list

**Extension examples**

- `ext/compare/v1.0.0` — A/B comparison (`compare:layers`, `compare:mode`, `compare:value`)
- `ext/chart/v1.0.0` — time-series statistics (`chart:layer`, `chart:area`, `chart:time`)
- `ext/raster-styling/v1.0.0` — per-layer palettes, min/max, squash

**Two MCP tools at the adapter boundary**

- `render_intent(intent)` → apply intent to the app; return any handle
- `get_state()` → return the app's current state as a `GeoIntent`

The agent only ever reads/writes `GeoIntent`. Every
application-specific concern lives in the adapter.

`[FIG: GeoUI Protocol architecture diagram — clean version of geoui-protocol-generic-interaction.md, showing top half (agent in GeoIntent), MCP boundary, adapter band, app-specific state, application. Vector graphic, not ASCII.]`

---

## 4. Worldview adapter — concrete instance

To validate the protocol, we wrap NASA Worldview behind a thin
adapter. Worldview already has a validated `WorldviewPermalinkInputSchema`
and a permalink URL wire format — the adapter just maps GeoIntent
↔ permalink input ↔ URL. **Worldview itself is unmodified.**

- `intent_to_url(GeoIntent) -> str` — emit a permalink
- `url_to_intent(str) -> GeoIntent` — parse Worldview's address bar back into intent
- MCP tools `geoui_render_intent` and `geoui_get_state` wrap these
- Agent navigates the live Worldview page via Playwright after `render_intent` returns a URL

**Iterative loop in practice** (refining turn):

1. Read current Worldview URL from the browser (`window.location.href`).
2. `get_state(url)` → parsed `GeoIntent`.
3. Modify only the fields the user changed (e.g. `time.instant`, `viewport.bbox`).
4. `render_intent(intent)` → new URL.
5. Navigate the browser to the new URL.

`[FIG: Worldview adapter diagram — clean version of worldview-geoui-interaction.md, showing GeoIntent on top, MCP layer, adapter band, WorldviewPermalinkInputSchema, URL, Worldview.]`

---

## 5. The comparison — protocol vs VLM-baseline

We benchmark the **same agent skeleton** on the **same set of
Worldview tasks**, varying only the *interaction mechanism*:

- **GeoUI variant** — uses `geoui_render_intent` / `geoui_get_state`. Two protocol tool calls per render.
- **VLM-baseline variant** — uses Playwright MCP directly: screenshot, accessibility snapshot, click, type, drag. No protocol.

**Discovery is held equal.** Both agents share CMR, vector-DB, and
Earthdata-search tools. The system prompts both include a
*fully-specified-intent fast-path* that skips the discovery loop
when the user provides exact layer IDs / verbose names + dates,
so the comparison isolates the **interaction mechanism**, not
intent extraction.

**Prompt suite — Core 6**, paired per agent:

| # | Task | What it stresses |
|---|---|---|
| 1 | Single-layer render | Floor / baseline |
| 2 | Date refinement | Temporal axis |
| 3 | Pan to a place | Spatial axis |
| 4 | A/B compare mode | First extension |
| 5 | Time-series chart | Second extension |
| 6 | Multi-layer overlay | List-complexity scaling |

Each prompt is given in two forms: GeoUI gets an exact registry
ID (e.g. `MODIS_Aqua_Aerosol_Optical_Depth_3km`); VLM gets the
verbose searchable name (e.g. *"MODIS Aqua Aerosol Optical
Depth 3km"*). Each side gets the input it can consume directly.

---

## 6. Results

`[FIG: the hero chart, again or larger here. log-scale grouped bars: GeoUI (1 turn), VLM (per-turn work turn), VLM (cumulative 2 turns), across {input, output, total, requests, tool calls, reasoning, cache-read}.]`

**Averaged over 4 workflows (yesterday's organic run + Core 1–3 today):**

|  | GeoUI (1 turn) | VLM (work turn) | VLM (cum., 2 turns) |
|---|---:|---:|---:|
| Input tokens | 48,224 | 677,285 | 838,801 |
| Output tokens | 2,448 | 15,949 | 18,101 |
| **Total tokens** | **50,672** | **693,234** | **856,903** |
| Requests | 6 | 30 | 36 |
| Tool calls | 4 | 49 | 60† |
| Reasoning tokens | 764 | 13,159 | 15,714† |
| Cache-read tokens | 35,872 | 619,936 | 848,000† |

† Cumulative columns: tool-call / reasoning / cache rows averaged over n=3 today-only workflows (yesterday's run didn't capture cumulative totals).

**Headline ratios per work turn**

- Raw tokens: **~14×** more for VLM
- Effective tokens (cache-adjusted at 0.1×): **~5–14×** depending on workflow
- Tool calls: **~10×** more
- LLM round-trips: **~5×** more
- Wall clock: **7–16×** longer

**Workflow-shape observation**

VLM agents tend to do **more clarification turns** before acting,
because a wrong click is expensive in pixels. Protocol agents
commit faster — fewer turns to the same end state.

---

## 7. Discussion

**What the protocol buys you beyond cost.**

- **Portability.** Replace the bottom half (adapter + app) with
  any other geospatial app; the agent is unchanged. The same
  `GeoIntent` flows across the MCP boundary regardless of target.
- **Auditability.** Logs contain validated typed fields, not
  pixels and DOM. Replays surface the same semantically
  meaningful state the agent saw.
- **Bounded capability.** Extensions are explicit URIs. An agent
  can't accidentally use a feature the application didn't declare.

**What it doesn't buy you.**

- Discovery is still expensive. CMR / metadata lookups dominate
  when the user's intent is underspecified. The protocol speeds
  up *applying* an intent, not *finding* one.
- The adapter is real engineering. Cost is paid once per app,
  but it's not free.

**Honest caveats**

- Single-digit number of benchmark runs per script (n ≈ 1–3) —
  variance bars not shown.
- Workflow set is hand-curated; the 6 prompts cover distinct
  axes but aren't a random sample.
- Token costs depend on model + prompt-cache pricing.
  Effective-cost figures assume a 10× cache discount typical of
  major providers as of this writing.

---

## 8. Future work

- **More applications.** Cesium / QGIS / Leaflet adapters to
  test the portability claim empirically rather than
  architecturally.
- **More extensions.** A `raster-arithmetic` extension for
  band-math is in design; a `temporal-aggregation` extension for
  time-binned statistics is a natural pairing for chart.
- **Real-user evaluation.** Token-cost is one dimension;
  task-success and user-perceived latency are the dimensions a
  scientist actually feels.
- **Protocol versioning** in production — `geoui_extensions`
  carries the URI version, so agents and adapters can evolve
  independently. Still needs a deprecation policy.

---

## 9. Demo & repo

`[QR: link to the live demo or the code repo. Maybe a 1-line caption: "Run the chat yourself: ./ieso_w_geoui/start.sh"]`

`[FIG: small screenshot of the marimo chat UI mid-turn — shows the agent's tool-trace collapsible, the rendered Worldview output, and the structured response.]`

---

## Layout sketch (informal)

```
┌─────────────────────────────────────────────────────────────┐
│                    TITLE  ·  AUTHORS  ·  LOGOS              │  full width
├──────────────┬───────────────────────┬─────────────────────┤
│  1. TL;DR    │  2. Motivation        │  3. GeoUI Protocol  │
│              │  (incl. side-by-side  │     core + ext      │
│              │   architecture pair)  │                     │
├──────────────┼───────────────────────┼─────────────────────┤
│  4. Worldview adapter (diagram)      │  5. Comparison      │
│                                      │     setup + table   │
├──────────────────────────────────────┴─────────────────────┤
│  6. Results  (hero chart + ratios table — full width)      │
├──────────────────────┬─────────────────────────────────────┤
│  7. Discussion       │  8. Future work                     │
├──────────────────────┴────────────────┬────────────────────┤
│  9. Demo  ·  QR  ·  contact info      │  refs / acks       │
└───────────────────────────────────────┴────────────────────┘
```

Three-column A0 portrait works; could also go two-column
landscape if the hero chart is the visual anchor.

---

## What's still needed (checklist)

- [ ] Author names + affiliations finalised
- [ ] Workshop poster ID (if assigned)
- [ ] Hero chart rendered (matplotlib, log-scale grouped bars — use the dict from earlier in chat)
- [ ] Architecture diagrams re-drawn as vector (current versions are ASCII; need clean SVGs)
- [ ] One marimo screenshot for §9
- [ ] QR code → repo / demo URL
- [ ] Pick visual medium (LaTeX beamerposter? typst? Inkscape SVG?)
- [ ] Color palette + typography decisions
- [ ] References (any prior work you want to cite — STAC, Worldview, AKD, etc.)
