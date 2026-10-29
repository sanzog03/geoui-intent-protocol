# GeoUI MapLibre demo

A plain React + TypeScript map (react-map-gl on MapLibre, NASA GIBS raster tiles) whose state is
attached to the GeoUI Intent Protocol with the [`@geoui/react`](../../sdk/geoui-react) SDK. It is
the second demo app of this repository: unlike NASA Worldview, nothing here is in the URL. An agent
reads and writes the app through `window.geoui`, which the GeoUI MCP in [`bridge/`](../../bridge)
reaches over Chrome DevTools Protocol.

## Run

```bash
npm install                        # once, at the repo root (npm workspaces)
npm run dev -w demo/maplibre       # http://127.0.0.1:5173
```

Then either drive it by hand (left panel), from the browser console
(`await geoui.render({layers: [{id: "Coastlines_15m"}], time: {instant: "2025-09-15"}})`), or from an
agent: start Chromium on CDP (`source demo/chromium.sh && ensure_chromium`), open the page in it, and
run the MCP with `GEOUI_APP_URL=http://127.0.0.1:5173 uv run geoui-bridge-mcp`.

## What it attaches

| Protocol field | App state | Notes |
|---|---|---|
| `viewport` | the map's bounds | a render calls `fitBounds` (no animation); the map's own move-end writes the exact bounds back |
| `time` | the selected date | `instant` only; a null (app default) becomes the default date |
| `layers` | the layer stack, bottom first | ids are GIBS layer ids (`src/layers.ts`); opacity maps to `raster-opacity` |
| `compare:*` | swipe between two synced maps | `compare:layers` and `compare:time` for the B side, `compare:value` moves the divider; `spy` and `opacity` modes fall back to swipe |
| `raster-styling:*` | stored and echoed per layer | shown in the layer list; min/max/squash/palettes are not applied to the tiles |

`chart` is not attached, so an agent that asks for it is told so by `window.geoui.render` and by the MCP.

## Layout

- `src/App.tsx` owns the state and calls the attach hooks.
- `src/layers.ts` is the catalogue published through `describe()`; `src/gibs.ts` builds tile URLs.
- `src/components/` MapView (one map), CompareSwipe (two maps + divider), Controls (the hand UI), StatePanel (`getState()` live).
