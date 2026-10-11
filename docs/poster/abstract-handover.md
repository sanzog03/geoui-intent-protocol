# Abstract Handover — `ieso_w_geoui` / GeoUI take

> Focused handover for **reworking an existing IESO-agent abstract**
> into a **GeoUI-Protocol abstract**. Companion to `HANDOVER.md`
> (which is for forking the protocol to a new adapter) and
> `poster-draft.md` (which is the long narrative). This doc is
> deliberately short and abstract-shaped.
>
> Source code: `ieso_w_geoui/` — protocol (`spec.md`, `core.py`),
> Worldview adapter (`adapter.py`), MCP tools (`tools.py`), agent
> (`agent.py`).

---

## The reframing (most important thing)

The old abstract is probably framed as:

> *"We built an IESO agent that drives NASA Worldview through its
> permalink URL grammar."*

The reworked abstract should be framed as:

> *"We introduce the **GeoUI Intent Protocol**, an
> application-agnostic declarative schema for agent-driven
> geospatial visualization. NASA Worldview is the reference
> adapter that demonstrates the protocol; the IESO agent is the
> validation vehicle."*

The **protocol is the contribution**. The IESO Worldview agent is
the *evidence* the protocol works. That flip is the whole rework.

---

## One-liner contribution

A typed declarative intent schema (`GeoIntent`) and two MCP tools
(`render_intent` / `get_state`) that let an LLM agent drive any
geospatial visualization through one bounded contract — instead
of through screenshots + DOM + clicks, or app-specific URL/RPC
grammars.

## Three sentences

LLM agents that drive geospatial visualizations either learn the
app's UI (expensive, brittle, app-specific) or emit a structured
intent that the app renders (cheap and portable — *if* a protocol
exists). We introduce the **GeoUI Intent Protocol**: a tiny
declarative core (`viewport`, `time`, `layers`) plus
URI-identified extensions (compare / chart / raster-styling),
STAC-inspired, exposed to agents as exactly two MCP tools —
`render_intent` and `get_state`. On iterative NASA Worldview
workflows (n=4), an agent that speaks GeoIntent costs **~14×
fewer raw tokens, ~10× fewer tool calls, and ~5× fewer LLM
round-trips per work turn** than the same agent driving the same
UI via screenshots + accessibility-tree snapshots, and answers
correctly on questions where the baseline cannot — because
geospatial viewers render through canvas + WebGL and semantic
map state is not recoverable from pixels.

---

## Section-by-section feed for the abstract body

### Problem (≈ 2 sentences)

- Earth-science workflows are **iterative**: a researcher refines
  date, region, layer set, compare mode across many turns.
- When an agent drives that loop, **how the agent talks to the
  application** is the dominant cost. Vision+DOM agents ship a
  fresh page snapshot into the model on every action.

### Contribution (≈ 2–3 sentences)

- **GeoUI Intent Protocol**: declarative intent schema for
  geospatial UIs.
- **STAC-inspired design**: tiny required core, URI-identified
  extensions, namespaced field prefixes (`compare:layers`,
  `chart:area`, `raster-styling:palettes`), independent
  versioning. Validators compose core + declared extensions
  (`allOf`).
- **Thin adapter pattern**: the app is unmodified. The adapter
  translates `GeoIntent ↔ app native state` (e.g. for Worldview,
  permalink URL). Two MCP tools at the boundary.

### Method (≈ 2 sentences)

- **Reference adapter** wraps NASA Worldview via its existing
  `WorldviewPermalinkInputSchema`. `intent_to_url` + `url_to_intent`
  round-trip cleanly on the supported field subset.
- **Same agent skeleton, same prompts, two interaction
  mechanisms**: GeoUI variant uses `geoui_render_intent` /
  `geoui_get_state`; baseline uses Playwright MCP directly
  (screenshot, accessibility snapshot, click, type, drag).
  Discovery tools (CMR, vector-DB, Earthdata-search) held equal.

### Results (≈ 2 sentences with numbers)

Averaged over 4 iterative Worldview workflows
(single-layer render, date refinement, spatial pan, A/B compare):

- **Total tokens per work turn:** 50,672 (GeoUI) vs **693,234**
  (VLM) — **~14×**.
- **Tool calls per work turn:** 4 vs **49** — **~10×**.
- **LLM round-trips per work turn:** 6 vs **30** — **~5×**.
- **Wall clock per work turn:** **7–16× longer** for VLM.
- Plus a qualitative accuracy result: on "what region am I
  viewing?" after a manual pan, `get_state()` answers from the
  Worldview URL the user landed on; the VLM-baseline cannot
  recover that semantic state from screenshots because Worldview
  renders through canvas + WebGL.

### Significance (≈ 2 sentences)

- **Portability:** the same agent drops onto Cesium, QGIS,
  Leaflet, Mapbox, … by writing one adapter. The protocol is the
  bounded contract; the app is unmodified.
- **Auditability and safety:** logs are validated typed fields,
  not pixels and DOM. Extensions are explicit URIs — agents
  can't use a capability the app didn't declare.

### Honest caveats (≈ 1 sentence)

- Small benchmark (n=4, hand-curated workflows). Token costs
  depend on model + cache pricing. The adapter is real
  engineering — cost paid once per app, but not free.

---

## Phrases to reuse (FOSS-friendly)

Pull these verbatim or paraphrase — they capture the angle the
abstract should land on:

- "GeoUI Intent Protocol"
- "Declarative geospatial intent schema"
- "STAC-inspired core + URI-identified extensions"
- "Thin adapter pattern"
- "Application-agnostic"
- "The agent only ever reads and writes `GeoIntent`"
- "App-specific concerns live strictly inside the adapter"
- "Two MCP tools at the adapter boundary"
- "Round-trip property: `intent → native → intent` is the
  identity"
- "Worldview as a reference adapter, not a special case"
- "Token-efficient, portable, and bounded by declared extensions"

## Phrases / framings to retire from the IESO version

These signal "IESO-agent paper" when you want "GeoUI-protocol
paper":

- ~~"We built an IESO agent for Worldview"~~ → "We built a
  protocol; Worldview is the first reference adapter."
- ~~"The agent emits Worldview permalink URLs"~~ → "The agent
  emits `GeoIntent`; the adapter emits Worldview permalinks."
- ~~"Iterative Worldview analysis assistant"~~ → "Iterative
  agent-driven geospatial analysis, demonstrated on Worldview."
- ~~Numbers framed as "agent X tokens"~~ → "interaction
  mechanism X tokens" (the protocol vs the VLM baseline; the
  agent itself is held constant in our benchmark).

## FOSS angle (for a FOSS-leaning venue)

- The **protocol spec is open** (`ieso_w_geoui/spec.md`, planned
  for hosting at `geoui.org/ext/...` URIs).
- **STAC lineage**: the FOSS geo community already speaks STAC's
  tiny-core + extensions idiom. GeoUI is the same shape applied
  one layer up the stack — agent ↔ visualization instead of
  client ↔ catalog.
- **Worldview is open** (NASA GIBS) — the reference
  implementation runs against a public, FOSS-compatible
  visualization stack.
- **Adapter cost amortizes across the ecosystem.** One adapter
  per FOSS map app (Leaflet, OpenLayers, Cesium, QGIS) and every
  GeoUI-aware agent inherits it.
- The **adapter recipe** (in `HANDOVER.md`) is short enough to
  hand to a maintainer of an existing FOSS map project as a
  porting guide.

---

## Title candidates (pick / mash up)

- **GeoUI Intent Protocol: a declarative, application-agnostic
  contract for agent-driven geospatial visualization**
- **From URL grammar to GeoIntent: token-efficient agentic
  control of geospatial UIs**
- **GeoUI: a STAC-inspired intent protocol for LLM agents driving
  geospatial visualization**
- **Agentic UI for GeoAI: an intent-driven framework for
  iterative geospatial analysis** *(current poster title — works
  as-is)*

---

## What `ieso_w_geoui/` actually contains (for grounding the
text in real artifacts)

| Path | Purpose |
|---|---|
| `spec.md` | Canonical v1.0.0 protocol spec — core + extension mechanics + versioning |
| `core.py` | `GeoIntent`, `Viewport`, `TimeWindow`, `LayerRef` Pydantic models |
| `extensions/{compare,chart,raster_styling}.py` | Three reference extensions (Pydantic + validators) |
| `adapter.py` | `intent_to_url` / `url_to_intent` — Worldview adapter |
| `url_parser.py` | Inverse of `WorldviewPermalinkTool.build_url`; closes the round-trip |
| `tools.py` | `GeoUIRenderIntentTool` / `GeoUIGetStateTool` (AKD `BaseTool` subclasses) |
| `agent.py` | `IESOWorldviewGeoUIAgent` — the validation-vehicle agent + Playwright MCP wiring |
| `notebooks/chat.py` | Marimo multi-turn chat — the live demo surface |
| `start.sh` | One-command: launch external Chromium + run notebook |

Everything else (benchmark prompts, runs, errors) is in the
sibling `benchmarks/` directory at the worktree root.

---

## Quick "draft a paragraph" templates

### Standalone 150-word paragraph

> LLM agents that drive geospatial visualizations face a recurring
> trade-off: learn the app's UI (expensive, brittle, app-specific)
> or speak through an app-specific URL/RPC grammar (portable only
> as far as the grammar goes). We introduce the **GeoUI Intent
> Protocol**, a STAC-inspired declarative schema that lets an
> agent drive any geospatial visualization through one bounded
> contract — `viewport`, `time`, `layers`, and URI-identified
> extensions for compare / chart / raster-styling — exposed via
> exactly two MCP tools (`render_intent` and `get_state`). A thin
> adapter translates GeoIntent to and from the application's
> native state; the application itself is unmodified. On
> iterative NASA Worldview workflows, an agent that speaks
> GeoIntent costs ~14× fewer raw tokens, ~10× fewer tool calls,
> and ~5× fewer LLM round-trips per work turn than the same agent
> driving the same UI via screenshots and accessibility-tree
> snapshots — and is also correct on questions the baseline
> cannot recover from pixels.

### Standalone 300-word paragraph

> *Add: 1 sentence on motivation; 1 sentence on the iterative
> Worldview workflow shape; 1 sentence on the discovery-held-equal
> benchmark setup; 1 sentence on extensions in practice (compare
> + chart + raster-styling); 1 sentence on portability beyond
> Worldview. Use the section-by-section feed above as
> ingredients.*

---

## What's still open (don't claim it in the abstract)

- VLM-baseline numbers come from `ieso_w_vlm/` runs against the
  same prompt suite — sample size is small (n=4), variance not
  reported.
- No published spec hosting yet — `geoui_extensions` URIs are
  placeholders. Don't claim a public registry.
- No second adapter shipped — portability is architectural, not
  empirically demonstrated across apps. Frame it as "the adapter
  pattern enables" rather than "we have shown across N apps."
- No formal conformance test suite. The conformance checklist
  in `HANDOVER.md` is a recipe, not a runnable harness.
