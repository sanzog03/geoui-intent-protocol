import { cleanup, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { extensions } from "../extensions";
import type { CompareFields, LayerRef, RasterStylingFields, TimeWindow, Viewport } from "../generated/geo-intent";
import { useGeoUIExtension, useGeoUILayerExtension, useGeoUILayers, useGeoUITime, useGeoUIViewport } from "../hooks";
import { GeoUIProvider, useGeoUIBridge, useGeoUIState } from "../provider";
import type { GeoUIBridge } from "../bridge";

declare global {
  var geoui: GeoUIBridge | undefined;
}

/** Call the bridge the way the MCP does: from outside React, with no act() scope holding back the commit. */
async function fromOutside<T>(fn: () => Promise<T>): Promise<T> {
  const g = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const previous = g.IS_REACT_ACT_ENVIRONMENT;
  g.IS_REACT_ACT_ENVIRONMENT = false;
  try {
    return await fn();
  } finally {
    g.IS_REACT_ACT_ENVIRONMENT = previous;
  }
}

const CATALOGUE = [
  { id: "A", title: "Layer A" },
  { id: "B", title: "Layer B" },
];

function App() {
  const [viewport, setViewport] = useState<Viewport>({ bbox: null, crs: "EPSG:4326" });
  const [time, setTime] = useState<TimeWindow | null>(null);
  const [layers, setLayers] = useState<LayerRef[]>([{ id: "A", visible: true, opacity: null }]);
  const [compare, setCompare] = useState<CompareFields | null>(null);
  const [styling, setStyling] = useState<Record<string, RasterStylingFields>>({});
  useGeoUIViewport(viewport, setViewport);
  useGeoUITime(time, setTime);
  useGeoUILayers(layers, setLayers);
  useGeoUIExtension(extensions.compare, compare, setCompare);
  useGeoUILayerExtension(extensions.rasterStyling, styling, setStyling);
  const state = useGeoUIState();
  const bridge = useGeoUIBridge();
  return (
    <>
      <pre data-testid="state">{JSON.stringify(state)}</pre>
      <span data-testid="ready">{String(bridge.ready)}</span>
    </>
  );
}

/** A slot whose setter ignores writes: nothing ever commits. */
function Stubborn() {
  const [layers] = useState<LayerRef[]>([]);
  useGeoUILayers(layers, () => {});
  return null;
}

afterEach(() => {
  cleanup();
});

describe("GeoUIProvider", () => {
  it("installs window.geoui, becomes ready after mount, and render() updates the app and resolves after the commit", async () => {
    render(
      <GeoUIProvider layers={CATALOGUE}>
        <App />
      </GeoUIProvider>,
    );
    const bridge = globalThis.geoui!;
    expect(bridge.ready).toBe(true);
    expect(bridge.describe().extensions.map((e) => e.name)).toEqual(["compare", "raster-styling"]);
    expect(bridge.describe().layers).toEqual(CATALOGUE);

    const result = await fromOutside(() =>
      bridge.render({
        viewport: { bbox: [-10, -5, 10, 5] },
        time: { instant: "2025-09-15" },
        layers: [{ id: "B", opacity: 0.4, "raster-styling:min": 0 }],
        "compare:layers": [{ id: "A" }],
        "compare:mode": "spy",
      }),
    );
    expect(result).toMatchObject({ ok: true, settled: true });
    const shown = JSON.parse(screen.getByTestId("state").textContent!);
    expect(shown.layers).toEqual([{ id: "B", visible: true, opacity: 0.4, "raster-styling:min": 0 }]);
    expect(shown["compare:layers"]).toEqual([{ id: "A" }]);
    expect(shown.time).toEqual({ instant: "2025-09-15" });
    expect(bridge.getState()).toEqual(shown);
    expect(screen.getByTestId("ready").textContent).toBe("true");
  });

  it("settles at once when the intent equals the current state", async () => {
    render(
      <GeoUIProvider layers={CATALOGUE} settleTimeoutMs={50}>
        <App />
      </GeoUIProvider>,
    );
    const bridge = globalThis.geoui!;
    const before = Date.now();
    const result = await fromOutside(() => bridge.render(bridge.getState()));
    expect(result).toMatchObject({ ok: true, settled: true });
    expect(Date.now() - before).toBeLessThan(50);
  });

  it("rejects what the app did not attach or does not know", async () => {
    render(
      <GeoUIProvider layers={CATALOGUE}>
        <App />
      </GeoUIProvider>,
    );
    const bridge = globalThis.geoui!;
    expect(await fromOutside(() => bridge.render({ "chart:layer": "A" }))).toMatchObject({ ok: false, code: "unsupported_extension" });
    expect(await fromOutside(() => bridge.render({ layers: [{ id: "Z" }] }))).toMatchObject({ ok: false, code: "unknown_layer" });
  });

  it("reports settled:false when the app never commits the write", async () => {
    render(
      <GeoUIProvider settleTimeoutMs={20}>
        <Stubborn />
      </GeoUIProvider>,
    );
    const result = await fromOutside(() => globalThis.geoui!.render({ layers: [{ id: "A" }] }));
    expect(result).toMatchObject({ ok: true, settled: false });
  });

  it("detaches slots on unmount and removes window.geoui with the provider", () => {
    const { unmount } = render(
      <GeoUIProvider layers={CATALOGUE}>
        <App />
      </GeoUIProvider>,
    );
    expect(globalThis.geoui).toBeDefined();
    unmount();
    expect(globalThis.geoui).toBeUndefined();
  });

  it("throws a clear error when a hook is used outside the provider", () => {
    expect(() => render(<App />)).toThrow(/inside <GeoUIProvider>/);
  });
});
