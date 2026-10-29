# `@geoui/react-adapter` — the GeoUI adapter SDK for React apps

Attach the state your app already has to the [GeoUI Intent Protocol](../../docs/spec.md), so an
agent can read it and write it as one `GeoIntent`. The SDK owns no state: you keep your `useState`,
reducer or store, and register a getter and a setter for each protocol field. The SDK composes
those into `window.geoui`, which anything with a handle on the page (the GeoUI MCP in
[`demo/maplibre`](../../demo/maplibre) over Chrome DevTools Protocol, a browser extension, the
console) calls.

Nothing is in the URL and nothing is sent anywhere: the protocol lives in the page.

## Install

Inside this repository the package is an npm workspace; apps consume it from source through a
Vite alias (see [`demo/maplibre/maplibre_geo_application/vite.config.ts`](../../demo/maplibre/maplibre_geo_application/vite.config.ts)).
Outside it, `npm run build` produces `dist/` and the package can be installed from a tarball or a
git URL; `react >= 18` is the only peer dependency.

## Three steps for an existing app

### 1. Wrap the tree in `GeoUIProvider` and give it your layer catalogue

```tsx
import { GeoUIProvider, type LayerCatalogueEntry } from "@geoui/react-adapter";

const LAYERS: LayerCatalogueEntry[] = [
  { id: "MODIS_Terra_CorrectedReflectance_TrueColor", title: "Terra true color (MODIS)", time: { start: "2000-02-24", period: "P1D" } },
  { id: "Coastlines_15m", title: "Coastlines" },
];

export function Root() {
  return (
    <GeoUIProvider layers={LAYERS}>
      <App />
    </GeoUIProvider>
  );
}
```

The provider creates one registry for the tree, installs `window.geoui`, and marks it ready once
the children have mounted. `layers` is what an agent sees in `describe().layers` and what
`render()` checks layer ids against; ids are whatever your app understands (GIBS ids in the demo).

Props: `layers` (catalogue), `validate` (an app-level check run last, return a message to reject),
`settleTimeoutMs` (how long `render()` waits for React to commit, default 2000), `install`
(false to keep `window.geoui` off and drive the registry yourself).

### 2. Attach each protocol field where its state lives

```tsx
import { extensions, useGeoUIExtension, useGeoUILayerExtension, useGeoUILayers, useGeoUITime, useGeoUIViewport } from "@geoui/react-adapter";
import type { CompareFields, LayerRef, RasterStylingFields, TimeWindow, Viewport } from "@geoui/react-adapter";

function App() {
  const [viewport, setViewport] = useState<Viewport>({ bbox: null, crs: "EPSG:4326" });
  const [time, setTime] = useState<TimeWindow | null>(null);
  const [layers, setLayers] = useState<LayerRef[]>([{ id: "Coastlines_15m" }]);
  const [compare, setCompare] = useState<CompareFields | null>(null);
  const [styling, setStyling] = useState<Record<string, RasterStylingFields>>({});

  useGeoUIViewport(viewport, setViewport);                        // bbox [west, south, east, north] + crs
  useGeoUITime(time, setTime);                                    // {instant} or {start, end}; null = app default
  useGeoUILayers(layers, setLayers);                              // the stack, bottom first: id, visible, opacity
  useGeoUIExtension(extensions.compare, compare, setCompare);     // intent-scoped extension, null = not in use
  useGeoUILayerExtension(extensions.rasterStyling, styling, setStyling); // layer-scoped: fields per layer id
  // ...
}
```

Each hook registers a *slot*: `get` reads your value through a ref synced after every commit, `set`
calls your setter. The hooks do not re-render anything themselves and do not care how the state is
held, so they fit an app that already exists; call them in the component that owns the state (or
in a small component that reads a store and writes back to it).

**Which extensions the agent sees is decided here.** The registry's catalogue is the set of specs
passed to the extension hooks that are currently mounted, nothing else: attach `extensions.compare`
and `compare:*` fields become valid and appear in `describe().extensions` and in
`geoui_extensions` of every `getState()`; leave `extensions.chart` unattached and a `chart:*`
field is refused with `unsupported_extension`. The shipped specs (`compare`, `chart`,
`rasterStyling`) are generated from [`schemas/extensions`](../../schemas/extensions), the same
documents the Python library describes.

### 3. Make the setters accept a whole value

`render()` **replaces** state, like loading a permalink: every attached slot is set from the
intent, and a field the intent leaves out resets to its default (`layers: []`, `time: null`,
`bbox: null`, extension `null` / `{}`). Your setters therefore receive complete values, not
patches. If your app derives something from a field (tile URLs from the date, a `fitBounds` from
the bbox), derive it in an effect on that state, so a render and a user action take the same
path. The demo's [`App.tsx`](../../demo/maplibre/maplibre_geo_application/src/App.tsx) and
[`MapView.tsx`](../../demo/maplibre/maplibre_geo_application/src/components/MapView.tsx) show
this for a map that is otherwise uncontrolled.

That is the whole integration. Open the page in Chromium, run `await geoui.getState()` in the
console, and you should see your state as a `GeoIntent`.

## What `window.geoui` exposes

| Member | Returns | Notes |
|---|---|---|
| `version`, `protocol`, `ready` | strings, boolean | SDK version, `geoui_version`, provider mounted |
| `describe()` | `{version, protocol, extensions, layers}` | the attached extension specs (name, uri, scope, keys, required, fields JSON Schema) and the layer catalogue |
| `getState()` | `GeoIntent` | composed from every slot right now; `geoui_extensions` lists the attached URIs |
| `render(intent)` | `Promise<{ok: true, state, settled} \| {ok: false, code, error}>` | validate, apply, wait for the commit, compose; never throws |

`render` error codes: `not_ready`, `invalid_intent`, `unsupported_extension`, `unknown_layer`,
`unsupported_value`. The messages use the same wording as the Python `prepare_intent`, so an agent
reads the same sentence whichever side rejects. `settled: false` means the commit did not happen
within `settleTimeoutMs` (the state was still applied).

## Driving it from an agent

Nothing more is needed in the app. Start Chromium with a DevTools port (`demo/chromium.sh` does
`--remote-debugging-port=9222`), open the page, and run the GeoUI MCP with the page's origin:

```bash
GEOUI_APP_URL=http://127.0.0.1:5173 uv run maplibre-mcp        # stdio MCP for Claude Code or any host
```

It finds the tab by origin (or opens one), and serves `geo_ui_list_intent_extensions_tool`
(= `describe()`), `geo_ui_get_state_tool` (= `getState()`) and `geo_ui_render_intent_tool`
(= `render()`, after checking the intent against the library). A pydantic-ai agent uses the same
three tools in-process (`maplibre.tools.pai`); `demo/maplibre/agents/maplibre_agent.py` is the
complete example and only its prompt names MapLibre.

## In the app's own UI

- `useGeoUIState()` returns the composed `GeoIntent` and re-renders after every commit (the demo's
  state panel).
- `useGeoUIBridge()` returns the same object as `window.geoui`, for a debug view or an in-page
  "apply this intent" control.

## Without React

The registry and the bridge are plain TypeScript. Create one with `createRegistry({layers})`,
register slots with `registry.attach({kind, spec?, get, set})` (kinds: `viewport`, `time`,
`layers`, `extension`, `layerExtension`), call `registry.markReady()` once and
`registry.markSettled()` after each state commit, and expose it with
`installBridge(registry)`. That is all the React layer does; a store-based adapter (deck.gl,
Redux, a global store scanned at build time) is the planned next step on top of these calls.

## Layout

- `src/registry.ts`: slots, `compose`, `validate`, `apply` (replace semantics), `settle`, `describe`.
- `src/bridge.ts`: `window.geoui` (`createBridge`, `installBridge`).
- `src/provider.tsx`, `src/hooks.ts`: the React layer.
- `src/extensions.ts`, `src/errors.ts`: the shipped specs and the agent-facing messages.
- `src/generated/`: types and schema literals produced by `npm run gen:types` from `schemas/`;
  `src/__tests__/schemas.test.ts` fails when they drift.

```bash
npm test -w @geoui/react-adapter        # vitest + jsdom; the bridge is driven from outside React
npm run typecheck -w @geoui/react-adapter
npm run gen:types               # after a change to the pydantic models and scripts/export_schemas.py
```
