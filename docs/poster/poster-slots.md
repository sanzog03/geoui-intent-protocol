# Poster — template slot fill

Copy each slot directly into the PowerPoint/Keynote template.
Long-form source material lives in `poster-draft.md`.

---

## 1. Title

**GeoUI Intent Protocol**

*Subtitle (use if the template has a subtitle slot):*
**Token Efficiency and Accuracy for Agentic Geospatial Visualization**

---

## 2. Authors + affiliation

Sanjog Thapa¹, Kumar [Last]¹, Nish [Last]¹, Rohit [Last]¹, Iksha [Last]¹, Rahul [Last]¹

¹ *NASA Office of Data Science and Informatics · The University of Alabama in Huntsville*

> Co-author last names are still TBC — `[Last]` placeholders
> can be filled in directly in the PowerPoint slide once
> confirmed.

---

## 3. Contact

sanjog.thapa@uah.edu

*(Optional second line — e.g., a repo or demo URL — if the template's contact box has room.)*

---

## 4. My Most Important Point (plain language)

> **Letting an LLM agent and a geospatial application
> communicate through a typed *intent* — instead of
> screenshots, DOM, and clicks — delivers both lower token
> cost (~15× per task) and higher answer accuracy on
> iterative analysis workflows.**

---

## 5. Two image / diagram placeholders

### Image A — GeoUI Protocol architecture *(to render as vector)*

**Caption.** The GeoUI Intent Protocol. The agent reasons in
`GeoIntent` and exchanges it with the application through two
MCP tools — `render_intent(intent)` and `get_state()`. A thin
**per-app adapter** translates between `GeoIntent` and the
application's native state. The geo-visualization application
itself requires no modification.

**Image credit.** Authors' own work, 2026.

> Source: `geoui-protocol-generic-interaction.md` (ASCII).
> Needs to be redrawn as a clean vector figure (D2 / SVG)
> for the poster.
>
> *Skipped, per current poster scope: the VLM-baseline
> diagram and the Worldview-specific instance diagram.*

### Image B — Benchmark results chart

**File:** `figs/results_chart.png`

**Caption.** Per-task cost on iterative NASA Worldview
workflows — GeoUI Intent Protocol vs. VLM + browser-control
baseline. Same agent, same tasks; only the interaction
mechanism varies. Averaged over n = 4 workflows; log-scale.
†*Cache-read, tool-call, and reasoning rows averaged over
n = 3 (today-only); the earlier organic-anchor run did not
capture cumulative totals for these series.*

**Image credit.** Authors' own work, 2026. Underlying data:
pydantic-ai turn-level logs (n = 4 workflows, GPT-4-class
model).

---

## 6. Why Important / Why I Did This

- **LLM agents that drive geospatial visualizations today rely
  on a VLM + browser-control loop** — screenshot, read the DOM,
  click, type. The pattern is general, but on geo apps it has
  two real failure modes.

- **Accuracy.** Geospatial viewers render the map through
  **canvas + WebGL**, which the DOM does not describe. Semantic
  map state — *which region is currently visible, which layers
  are on, at what date* — is therefore not recoverable from
  the DOM and unreliable from pixels. Basic questions such as
  *"what region am I looking at?"* return incorrect answers
  under the screenshot baseline.

- **Cost.** Every action ships a fresh page snapshot back into
  the model context. Token usage scales with **UI complexity
  and turn count**, not task complexity. Even basic tasks
  incur many agent ↔ browser round-trips.

- **A typed intent fixes the wrong end of the loop.** We
  designed and implemented the **GeoUI Intent Protocol** so
  that the agent and the application exchange a declarative
  `GeoIntent` payload — viewport, time, layers, styling —
  rather than screenshots and clicks.

- **Extensible by design**, inspired by **STAC extensions**:
  a small **core** describes layering and view; **named
  extensions** (e.g., compare-mode, charting, raster styling)
  add advanced capabilities, declared per intent.

---

## 7a. Background / Context *(replaces template "Text")*

The default architecture for LLM-driven geospatial analysis
pairs a vision-language model with browser automation: the
agent observes the page through screenshots and the
accessibility / DOM tree, then acts by clicking, typing, and
dragging. This pattern generalizes across web applications,
but breaks down on geospatial viewers such as NASA Worldview,
which render the map through **canvas + WebGL surfaces that
the DOM does not expose**. As a result, the agent cannot
recover semantic map state from its observations, and every
action ships a fresh page snapshot back into model context —
driving cost up and accuracy down.

The **GeoUI Intent Protocol** replaces this loop with a typed
contract between agent and application. Both sides exchange
a structured **`GeoIntent`** payload — viewport (bbox + CRS),
time, layers, and styling — through two MCP tools at the
boundary: **`render_intent(intent)`** applies the agent's
intent to the application, and **`get_state()`** returns the
application's current state in the same shape. A thin
**per-app adapter** translates between `GeoIntent` and the
application's native representation.

We instantiate the protocol against **NASA Worldview** via an
adapter that maps `GeoIntent` to Worldview's existing
permalink schema; **Worldview itself is unmodified**. The
schema is built to extend in the spirit of **STAC extensions**:
a small **core** covers layering, viewport, and time;
**namespaced extensions** (compare, chart, raster styling, …)
declare additional capability per intent.

---

## 7b. Data & Results *(replaces template "Text")*

**Experimental setup.** One agent — the **IESO Worldview
agent** — run as two variants: a **baseline** using
screenshots + DOM + Playwright browser control, and a
**treatment** using the GeoUI Intent Protocol. Discovery tools
(CMR, vector-DB) are held equal across variants, so the
comparison isolates the *interaction mechanism* rather than
the discovery loop.

**Workloads.** Four iterative Worldview queries: initial
single-layer render, date refinement, spatial pan, and one
organic anchor workflow.

### Result 1 — Token efficiency

Absolute cost per task, averaged over n = 4 workflows. GeoUI
completes each task in one work turn; VLM totals are
cumulative across the task's turns.

|  | GeoUI | VLM (cum. / task) | Ratio |
|---|---:|---:|---:|
| Input tokens | 48,224 | 838,801 | ~17× |
| Output tokens | 2,448 | 18,101 | ~7× |
| **Total tokens** | **50,672** | **856,903** | **~17×** |
| LLM round-trips | 6 | 36 | ~6× |
| Tool calls | 4 | 60† | ~15× |
| Reasoning tokens | 764 | 15,714† | ~21× |
| Cache-read tokens | 35,872 | 848,000† | ~24× |
| Wall clock | 1× | 7–16× | 7–16× |

†*Cumulative rows averaged over n = 3 (today-only); the
organic-anchor run did not capture these totals.*

*See the results chart (Image B) for the visual.*

### Result 2 — Accuracy

On tasks that depend on semantic map state, the screenshot
baseline is *plain wrong* in ways the protocol path is not.
After a spatial pan, when asked *"what region am I currently
viewing?"*, the VLM + screenshot variant cannot recover the
answer from pixels (no DOM, canvas-only content) and produces
a fabricated region. The protocol variant answers directly
from `get_state()`, since `viewport.bbox` is a structured
field.

> **Token efficiency** comes from the schema replacing screenshots.
> **Accuracy** comes from intent-driven context replacing pixels.

---

## 8. Conclusions

- The **GeoUI Intent Protocol** delivers, on iterative NASA
  Worldview workflows (n = 4), **~15× lower per-task cost**
  and **correct answers** on questions where the VLM +
  screenshot baseline returns wrong answers.

- The protocol additionally provides, by construction:
  - **Portability** — one protocol, many applications via
    per-app adapters.
  - **Auditability** — logs hold structured, validated fields
    rather than pixels and DOM.
  - **Bounded capability** — extensions are explicit, named
    URIs.

- **Limitations.** Four workflows; hand-curated workload set;
  token-cost figures depend on model and prompt-cache pricing.

- **Next.** Adapters for additional applications (Cesium,
  QGIS, Leaflet) to validate the portability claim; new
  extensions (`raster-arithmetic`, `temporal-aggregation`); a
  real-user task-success study.

---

## Checklist

- [x] Lead author: Sanjog Thapa (NASA ODSI · UAH)
- [x] Co-author affiliation: shared with Sanjog (NASA ODSI · UAH)
- [ ] Co-authors' last names (Kumar / Nish / Rohit / Iksha / Rahul)
- [ ] Confirm contact line (email only, or email + repo URL?)
- [ ] **Slot 5A:** redraw the generic GeoUI Protocol diagram
      as a clean vector figure (ASCII source in
      `geoui-protocol-generic-interaction.md`)
- [x] **Slot 5B:** benchmark results chart (token-efficiency)
      rendered → `figs/results_chart.png`
- [ ] **Accuracy evidence (Result 2).** Currently described in
      §7b as a qualitative claim ("VLM gets *plain wrong*").
      Decide: include a concrete example as a callout
      box / quote ("Q: *what region am I looking at?* — VLM:
      [wrong]; GeoUI: Gulf of Mexico"), and whether to back
      this with screenshots or a side-by-side log excerpt.
- [ ] References slot — if template has one, add: STAC,
      Worldview, MCP, pydantic-ai
