# Worldview ⇄ GeoUI Protocol — Interaction Diagram

Bidirectional flow between the IESO Worldview Agent and NASA Worldview via the
GeoUI Protocol. The agent reasons in `GeoIntent` only; a Worldview-side adapter
translates to/from the existing `WorldviewPermalinkInputSchema` and Worldview's
URL wire format.

```
              ┌──────────────────────────────────────────┐
              │         IESO Worldview Agent             │
              │   ────────────────────────────────────   │
              │   Reasons in GeoIntent only.             │
              │   Iterative loop: observe → plan → act.  │
              └────────────┬───────────────────┬─────────┘
                           │                   ▲
              emit         │                   │      ingest
              GeoIntent    │                   │      GeoIntent
                           ▼                   │
              ═════════════════ MCP ═══════════════════════
                           │                   │
                 ┌─────────┴──────────┐   ┌────┴───────────────┐
                 │ render_intent      │   │ get_state          │
                 │   (intent)         │   │   (url)            │
                 └─────────┬──────────┘   └────▲───────────────┘
   Worldview   ────────────┼───────────────────┼─────────────────
   adapter                 │  intent→input     │  input→intent
   (NEW)                   ▼                   │
              ┌──────────────────────────────────────────┐
              │  WorldviewPermalinkInputSchema           │
              │  (existing validated capability surface, │
              │   used unchanged)                        │
              └─────────┬───────────────────────▲────────┘
                        │ build_url             │ parse_url
                        ▼                       │
              ┌──────────────────────────────────────────┐
              │            Worldview URL                 │
              └─────────┬───────────────────────▲────────┘
                        │ open in browser       │ user-shared
                        ▼                       │  permalink
              ┌──────────────────────────────────────────┐
              │           NASA Worldview                 │
              │      (production app, unmodified)        │
              └──────────────────────────────────────────┘
```

## Reading the diagram

- **Top half (above the MCP line):** the agent's reasoning loop. It only ever
  produces or consumes `GeoIntent` — never sees Worldview-specific shapes.
  This is the bounded-capability contract.
- **MCP boundary:** the two new tools — `render_intent` (agent → app) and
  `get_state` (app → agent). The protocol's externally observable interface
  for the Worldview adapter.
- **Adapter band:** translates between portable `GeoIntent` and Worldview's
  existing `WorldviewPermalinkInputSchema`. Pure functions, no I/O. This is
  where Worldview-specific mapping lives.
- **Bottom half:** the existing permalink tool + Worldview itself, unchanged.
  URL is the wire format for both directions (emitted by `build_url`, parsed
  by a new `parse_url`).

## Portability claim

Any other geo-UI app would replace the entire bottom half (adapter +
app-specific schema + app) with its own adapter. The agent (top half) is
unchanged. The same `GeoIntent` flowing across the MCP line addresses any
conforming app.
