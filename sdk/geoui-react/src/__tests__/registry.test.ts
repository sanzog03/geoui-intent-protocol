import { describe, expect, it } from "vitest";
import { extensions } from "../extensions";
import type { GeoIntent, LayerRef, TimeWindow, Viewport } from "../generated/geo-intent";
import { COMPARE_SPEC, RASTER_STYLING_SPEC } from "../generated/schemas";
import { createRegistry, type Registry } from "../registry";
import { installBridge } from "../bridge";

/** A test app: plain variables standing in for React state, attached through slots. */
function app(registry: Registry, opts: { compare?: boolean; styling?: boolean } = {}) {
  const s = {
    viewport: { bbox: null, crs: "EPSG:4326" } as Viewport,
    time: null as TimeWindow | null,
    layers: [] as LayerRef[],
    compare: null as Record<string, unknown> | null,
    styling: {} as Record<string, Record<string, unknown>>,
  };
  registry.attach({ kind: "viewport", get: () => s.viewport, set: (v) => (s.viewport = v as Viewport) });
  registry.attach({ kind: "time", get: () => s.time, set: (v) => (s.time = v as TimeWindow | null) });
  registry.attach({ kind: "layers", get: () => s.layers, set: (v) => (s.layers = v as LayerRef[]) });
  if (opts.compare) {
    registry.attach({ kind: "extension", spec: extensions.compare, get: () => s.compare, set: (v) => (s.compare = v as never) });
  }
  if (opts.styling) {
    registry.attach({ kind: "layerExtension", spec: extensions.rasterStyling, get: () => s.styling, set: (v) => (s.styling = v as never) });
  }
  registry.markReady();
  return s;
}

const CATALOGUE = [
  { id: "A", title: "Layer A" },
  { id: "B", title: "Layer B", time: { start: "2000-01-01", end: null, period: "P1D" } },
];

describe("compose", () => {
  it("has protocol defaults when nothing is attached but the core slots", () => {
    const r = createRegistry();
    app(r);
    expect(r.compose()).toEqual({
      geoui_version: "1.0.0",
      geoui_extensions: [],
      viewport: { bbox: null, crs: "EPSG:4326" },
      time: null,
      layers: [],
    });
  });

  it("declares attached extensions in attach order and spreads both scopes as namespaced keys", () => {
    const r = createRegistry();
    const s = app(r, { compare: true, styling: true });
    s.layers = [{ id: "A", visible: true, opacity: 0.5 }, { id: "B" }];
    s.time = { instant: "2025-09-15" };
    s.compare = { layers: [{ id: "B" }], mode: "swipe", value: 50, time: null };
    s.styling = { A: { min: 0, max: 2, squash: true, palettes: null } };
    const out = r.compose();
    expect(out.geoui_extensions).toEqual([COMPARE_SPEC.uri, RASTER_STYLING_SPEC.uri]);
    expect(out["compare:layers"]).toEqual([{ id: "B" }]);
    expect(out["compare:mode"]).toBe("swipe");
    expect(out).not.toHaveProperty("compare:time"); // null fields are omitted
    expect(out.layers).toEqual([
      { id: "A", visible: true, opacity: 0.5, "raster-styling:min": 0, "raster-styling:max": 2, "raster-styling:squash": true },
      { id: "B" },
    ]);
  });
});

describe("describe", () => {
  it("returns the attached specs verbatim plus the layer catalogue", () => {
    const r = createRegistry({ layers: CATALOGUE });
    app(r, { compare: true, styling: true });
    const d = r.describe();
    expect(d.protocol).toBe("1.0.0");
    expect(d.extensions).toEqual([COMPARE_SPEC, RASTER_STYLING_SPEC]);
    expect(d.layers).toEqual(CATALOGUE);
  });
});

describe("validate", () => {
  it("rejects non-objects", () => {
    const r = createRegistry();
    app(r);
    expect(r.validate(null)).toMatchObject({ ok: false, code: "invalid_intent" });
    expect(r.validate([1])).toMatchObject({ ok: false, code: "invalid_intent" });
    expect(r.validate({ layers: "A" })).toMatchObject({ ok: false, code: "invalid_intent" });
  });

  it("rejects extensions the app did not attach, naming the supported ones", () => {
    const r = createRegistry();
    app(r, { compare: true, styling: true });
    const res = r.validate({ "chart:layer": "A", layers: [{ id: "A", "elevation:exaggeration": 2 }] });
    expect(res).toEqual({
      ok: false,
      code: "unsupported_extension",
      error: "extension(s) ['chart', 'elevation'] are not available in this app; supported: compare, raster-styling (see geo_ui_list_intent_extensions_tool)",
    });
  });

  it("rejects a used extension with a required key missing", () => {
    const r = createRegistry();
    app(r, { compare: true });
    expect(r.validate({ "compare:mode": "spy" })).toEqual({
      ok: false,
      code: "invalid_intent",
      error: "extension compare requires compare:layers",
    });
  });

  it("rejects a CRS other than EPSG:4326", () => {
    const r = createRegistry();
    app(r);
    expect(r.validate({ viewport: { bbox: null, crs: "EPSG:3857" } })).toEqual({
      ok: false,
      code: "unsupported_value",
      error: "viewport.crs 'EPSG:3857' is not supported by this app; use EPSG:4326",
    });
  });

  it("rejects unknown layer ids on the root and inside compare:layers when a catalogue was given", () => {
    const r = createRegistry({ layers: CATALOGUE });
    app(r, { compare: true });
    expect(r.validate({ layers: [{ id: "A" }, { id: "Z" }], "compare:layers": [{ id: "Q" }] })).toEqual({
      ok: false,
      code: "unknown_layer",
      error: "unknown layer id(s) ['Z', 'Q']; known ids: A, B (see geo_ui_list_intent_extensions_tool)",
    });
    const noCatalogue = createRegistry();
    app(noCatalogue);
    expect(noCatalogue.validate({ layers: [{ id: "anything" }] }).ok).toBe(true);
  });

  it("runs the app's own check last and reports it as unsupported_value", () => {
    const r = createRegistry({ validate: (i) => (i.layers && i.layers.length > 1 ? "only one layer at a time" : null) });
    app(r);
    expect(r.validate({ layers: [{ id: "A" }, { id: "B" }] })).toEqual({ ok: false, code: "unsupported_value", error: "only one layer at a time" });
  });

  it("ignores geoui_extensions in the incoming document", () => {
    const r = createRegistry();
    app(r);
    expect(r.validate({ geoui_extensions: ["https://example.org/ext/foo/v1"], layers: [] }).ok).toBe(true);
  });
});

describe("apply (replace semantics)", () => {
  it("sets every slot from the intent and resets absent fields to defaults", () => {
    const r = createRegistry();
    const s = app(r, { compare: true, styling: true });
    const full: GeoIntent = {
      viewport: { bbox: [-10, -5, 10, 5], crs: "EPSG:4326" },
      time: { instant: "2025-09-15", start: null, end: null },
      layers: [{ id: "A", opacity: 0.3, "raster-styling:min": 1 }, { id: "B", visible: false }],
      "compare:layers": [{ id: "B" }],
      "compare:mode": "spy",
    };
    r.apply(full);
    expect(s.viewport).toEqual({ bbox: [-10, -5, 10, 5], crs: "EPSG:4326" });
    expect(s.time).toEqual({ instant: "2025-09-15" }); // nulls dropped
    expect(s.layers).toEqual([{ id: "A", visible: true, opacity: 0.3 }, { id: "B", visible: false, opacity: null }]); // core only
    expect(s.compare).toEqual({ layers: [{ id: "B" }], mode: "spy" });
    expect(s.styling).toEqual({ A: { min: 1 } });

    r.apply({ layers: [{ id: "A" }] });
    expect(s.viewport).toEqual({ bbox: null, crs: "EPSG:4326" });
    expect(s.time).toBeNull();
    expect(s.compare).toBeNull();
    expect(s.styling).toEqual({});
  });
});

describe("render", () => {
  it("validates, applies, waits for a commit and returns the composed state", async () => {
    const r = createRegistry({ layers: CATALOGUE });
    const s = app(r, { compare: true });
    const p = r.render({ layers: [{ id: "A" }], time: { instant: "2025-01-01" } }, 1000);
    expect(s.layers).toEqual([{ id: "A", visible: true, opacity: null }]); // applied synchronously
    r.markSettled();
    const out = await p;
    expect(out).toEqual({
      ok: true,
      settled: true,
      state: { geoui_version: "1.0.0", geoui_extensions: [COMPARE_SPEC.uri], viewport: { bbox: null, crs: "EPSG:4326" }, time: { instant: "2025-01-01" }, layers: [{ id: "A", visible: true, opacity: null }] },
    });
  });

  it("reports settled:false after the timeout when nothing commits", async () => {
    const r = createRegistry();
    app(r);
    const out = await r.render({ layers: [] }, 10);
    expect(out).toMatchObject({ ok: true, settled: false });
  });

  it("never throws: validation failures come back as results", async () => {
    const r = createRegistry();
    app(r);
    expect(await r.render("nope", 10)).toMatchObject({ ok: false, code: "invalid_intent" });
  });

  it("is not_ready before the provider marks the registry ready", async () => {
    const r = createRegistry();
    expect(await r.render({ layers: [] }, 10)).toEqual({ ok: false, code: "not_ready", error: "the GeoUI provider is not mounted yet" });
  });
});

describe("installBridge", () => {
  it("exposes window.geoui with describe/getState/render and uninstalls cleanly", async () => {
    const r = createRegistry({ layers: CATALOGUE });
    app(r, { compare: true });
    const target = {} as Window & { geoui?: unknown };
    const uninstall = installBridge(r, target);
    const bridge = target.geoui as { ready: boolean; protocol: string; version: string; describe: () => unknown; getState: () => GeoIntent; render: (i: unknown) => Promise<unknown> };
    expect(bridge.ready).toBe(true);
    expect(bridge.protocol).toBe("1.0.0");
    expect(bridge.version).toMatch(/^\d+\.\d+\.\d+/);
    expect((bridge.describe() as { layers: unknown }).layers).toEqual(CATALOGUE);
    const p = bridge.render({ layers: [{ id: "B" }] });
    r.markSettled();
    expect(await p).toMatchObject({ ok: true });
    expect(bridge.getState().layers).toEqual([{ id: "B", visible: true, opacity: null }]);
    uninstall();
    expect(target.geoui).toBeUndefined();
  });
});
