# Worldview ⇄ VLM Baseline — Interaction Diagram

Bidirectional flow between the IESO Worldview Agent and NASA Worldview when
the agent uses **raw DOM HTML + visual snapshots** as state context (no
intermediate protocol). Browser automation replaces the schema adapter as the
integration mechanism.

```
              ┌──────────────────────────────────────────┐
              │   IESO Worldview Agent (ssc baseline)    │
              │   ────────────────────────────────────   │
              │   Reasons over screenshot + DOM HTML.    │
              │   Must know Worldview URL grammar to act.│
              │   Iterative loop: observe → plan → act.  │
              └──────────┬───────────────────┬───────────┘
                         │                   ▲
              emit       │                   │     ingest
              permalink  │                   │     { screenshot, dom }
              (text)     │                   │     (large multimodal context)
                         ▼                   │
              ═════════════════ MCP ════════════════════════
                         │                   │
               ┌─────────┴────────┐    ┌─────┴───────────────┐
               │ navigate(url)    │    │ capture_state       │
               └─────────┬────────┘    └─────▲───────────────┘
  Browser     ───────────┼────────────────────┼─────────────────
  automation             │ page.goto()        │ page.screenshot()
  (Playwright /          │                    │ page.content()
   similar, NEW)         ▼                    │
              ┌──────────────────────────────────────────┐
              │           Headless browser               │
              │   ┌──────────────────────────────────┐   │
              │   │        NASA Worldview            │   │
              │   │   (production app, unmodified)   │   │
              │   │   rendered DOM + visual canvas   │   │
              │   └──────────────────────────────────┘   │
              └──────────────────────────────────────────┘
```

## Reading the diagram

- **Top half (above the MCP line):** the agent's reasoning loop. The agent's
  context window is filled with a **screenshot** (vision tokens) and the
  **raw DOM HTML** (text tokens) of the rendered page. No portable
  intermediate representation — context is Worldview-shaped on the way in.
- **MCP boundary:** the two browser-automation tools.
  - `navigate(url)` — open a Worldview URL in the headless browser. Requires
    the agent to know Worldview's permalink grammar to construct `url`.
  - `capture_state()` — return `{ screenshot, dom }` from the current page.
- **Browser-automation band:** Playwright (or similar) drives a headless
  browser; `page.goto`, `page.screenshot`, `page.content` are the underlying
  primitives.
- **Bottom half:** Worldview itself, running unmodified inside a real browser
  context (not just a URL string).

## What the agent pays per turn

State ingestion drops a large multimodal payload into the agent's context:

- **Screenshot:** hundreds to several thousand vision tokens depending on
  resolution (vision tokens are typically priced higher than text tokens).
- **DOM HTML:** Worldview is a non-trivial single-page React app. A captured
  DOM commonly runs tens of thousands of text tokens, often most of which is
  framework chrome and irrelevant to the user's intent.

A single ingest can easily exceed 10k–50k tokens before the agent has done
any reasoning. Cost compounds linearly across an iterative analysis.

## Contrast with the GeoUI Protocol path

- **No bounded contract.** The agent ingests Worldview-specific artifacts
  directly. Its understanding of "current state" is implicit in vision +
  markup, not in a finite validated schema.
- **No portability.** A different geo-viz application would require the
  agent to learn a different DOM and different visual conventions —
  swapping the adapter is not enough.
- **Action surface coupling.** The agent must know Worldview's URL grammar
  to act, even though state observation is generic browser automation.
- **Auditability is shallow.** State is captured as pixels + markup, not as
  semantically meaningful fields, so downstream logging and replay surface
  the same opaque artifacts the agent saw.
