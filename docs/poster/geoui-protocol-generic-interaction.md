# GeoUI Protocol — Generic Interaction Diagram

The application-agnostic shape of the GeoUI Protocol. An agent reasons in
`GeoIntent` only; an app-specific adapter translates to and from the
application's native state representation. Any conforming geo-visualization
application slots into the bottom half by providing its own adapter.

```
              ┌──────────────────────────────────────────┐
              │                  Agent                   │
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
                 │   (intent)         │   │   ()               │
                 └─────────┬──────────┘   └────▲───────────────┘
   App         ────────────┼───────────────────┼─────────────────
   adapter                 │  intent→state     │  state→intent
                           ▼                   │
              ┌──────────────────────────────────────────┐
              │  App-specific state representation       │
              │  (the application's native, validated    │
              │   shape; encoded/decoded by the adapter) │
              └─────────┬───────────────────────▲────────┘
                        │ apply                 │ observe
                        ▼                       │
              ┌──────────────────────────────────────────┐
              │     Geo-visualization application        │
              │       (no modification required)         │
              └──────────────────────────────────────────┘
```

## Reading the diagram

- **Top half (above the MCP line):** the agent's reasoning loop. It only ever
  produces or consumes `GeoIntent` — never sees app-specific shapes. This is
  the bounded-capability contract.
- **MCP boundary:** two protocol tools an adapter MUST implement.
  - `render_intent(intent)` — accept a `GeoIntent` and apply it to the
    application. Return identifier(s) for the resulting state if applicable.
  - `get_state()` — return the application's current state as a `GeoIntent`.
- **Adapter band:** translates between portable `GeoIntent` and the
  application's native state representation. Pure functions, no I/O. This is
  the only Worldview/Cesium/QGIS/etc.-specific code in the system.
- **Bottom half:** the application's native state and the application itself,
  used unmodified.

## What an adapter provides

An adapter for an application MUST:

1. Define the mapping from `GeoIntent` (core + declared extensions) into the
   application's native state representation.
2. Define the inverse mapping from the application's current state back into
   a valid `GeoIntent`, lossy where necessary but never silently wrong.
3. Implement the `render_intent` and `get_state` MCP tools as thin wrappers
   over (1) and (2).
4. Declare which extension URIs it supports — i.e., which capability
   surface beyond the core it exposes.

Nothing else changes. The agent is unaware of the application's identity.

## Portability claim

Replacing one application with another (or running multiple in parallel)
requires only a new adapter. The agent, the protocol, the extensions, and the
benchmarking harness are all reusable. This is the architectural payoff that
distinguishes the GeoUI Protocol path from approaches in which the agent
ingests application-specific artifacts directly.

## Concrete instances

- [Worldview adapter](./worldview-geoui-interaction.md) — the bottom half is
  Worldview's permalink schema + URL wire format + NASA Worldview, plumbed
  to the same MCP surface shown above.
