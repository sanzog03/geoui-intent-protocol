/**
 * The registry: what the app attached, composed into one GeoIntent and applied back from one.
 *
 * The app owns its state. Each hook registers a *slot* (a getter and a setter for one protocol
 * field or one extension); `compose()` reads every slot into a GeoIntent, `apply()` writes a
 * GeoIntent into every slot (replace semantics: absent fields reset to their defaults), and
 * `render()` is validate → apply → settle → compose. No React here: the provider calls
 * `markReady()` once mounted and `markSettled()` after every commit.
 */
import type { ExtensionSpec } from "./extensions";
import { fail, messages, type RenderError } from "./errors";
import type { GeoIntent, LayerRef, TimeWindow, Viewport } from "./generated/geo-intent";
import { PROTOCOL_VERSION, SDK_VERSION } from "./version";

export type SlotKind = "viewport" | "time" | "layers" | "extension" | "layerExtension";

export interface Slot {
  kind: SlotKind;
  /** Required for the two extension kinds. */
  spec?: ExtensionSpec<unknown>;
  get(): unknown;
  set(value: unknown): void;
}

export interface LayerCatalogueEntry {
  id: string;
  title: string;
  time?: { start: string; end?: string | null; period?: string };
}

export interface Catalogue {
  version: string;
  protocol: string;
  extensions: ExtensionSpec[];
  layers: LayerCatalogueEntry[];
}

export type ValidateResult = { ok: true; intent: GeoIntent } | RenderError;
export type RenderResult = { ok: true; state: GeoIntent; settled: boolean } | RenderError;

export interface RegistryOptions {
  /** The app's layer catalogue. When given, unknown layer ids are rejected. */
  layers?: LayerCatalogueEntry[];
  /** An app-level check run last; return a message to reject the intent as `unsupported_value`. */
  validate?: (intent: GeoIntent) => string | null;
}

export interface Registry {
  attach(slot: Slot): () => void;
  /** Replace the options (the provider calls this when its props change). */
  configure(options: RegistryOptions): void;
  compose(): GeoIntent;
  describe(): Catalogue;
  validate(intent: unknown): ValidateResult;
  /** Write the intent into every slot. Returns false when no slot value changed (nothing will commit). */
  apply(intent: GeoIntent): boolean;
  settle(timeoutMs: number): Promise<boolean>;
  render(intent: unknown, settleTimeoutMs?: number): Promise<RenderResult>;
  markReady(): void;
  markSettled(): void;
  readonly ready: boolean;
  /** Notified after every commit (and every attach/detach); for useSyncExternalStore. */
  subscribe(listener: () => void): () => void;
  /** `compose()` cached until the next commit, so React can compare snapshots by identity. */
  snapshot(): GeoIntent;
}

export const DEFAULT_SETTLE_TIMEOUT_MS = 2000;
const DEFAULT_CRS = "EPSG:4326";

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const defined = (v: unknown) => v !== null && v !== undefined;

function prefixed(obj: Record<string, unknown>, prefix: string): Record<string, unknown> {
  const marker = `${prefix}:`;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (key.startsWith(marker) && defined(value)) out[key.slice(marker.length)] = value;
  }
  return out;
}

function spread(fields: Record<string, unknown>, prefix: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(fields)) {
    if (defined(value)) out[`${prefix}:${key}`] = value;
  }
  return out;
}

function prefixesIn(obj: Record<string, unknown>): string[] {
  return Object.keys(obj)
    .filter((k) => k.includes(":"))
    .map((k) => k.split(":", 1)[0] as string);
}

function normalizeTime(time: unknown): TimeWindow | null {
  if (!isObject(time)) return null;
  const out: TimeWindow = {};
  for (const key of ["instant", "start", "end"] as const) {
    if (defined(time[key])) out[key] = time[key] as string;
  }
  return Object.keys(out).length ? out : null;
}

function normalizeViewport(viewport: unknown): Viewport {
  if (!isObject(viewport)) return { bbox: null, crs: DEFAULT_CRS };
  return { bbox: (viewport.bbox as Viewport["bbox"]) ?? null, crs: (viewport.crs as string | undefined) ?? DEFAULT_CRS };
}

function coreLayer(layer: Record<string, unknown>): LayerRef {
  return { id: String(layer.id), visible: (layer.visible as boolean | undefined) ?? true, opacity: (layer.opacity as number | null | undefined) ?? null };
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export function createRegistry(initial: RegistryOptions = {}): Registry {
  let options: RegistryOptions = { ...initial };
  const slots: Slot[] = [];
  let ready = false;
  let waiters: Array<(settled: boolean) => void> = [];
  const listeners = new Set<() => void>();
  let cached: GeoIntent | null = null;

  // Recompose and notify only when the result differs: hooks call markSettled after every commit,
  // including the commits this notification causes, so this must be idempotent.
  const invalidate = () => {
    const fresh = compose();
    if (cached !== null && same(cached, fresh)) return;
    cached = fresh;
    for (const listener of listeners) listener();
  };

  const extensionSlots = () => slots.filter((s) => s.kind === "extension" || s.kind === "layerExtension") as Array<Slot & { spec: ExtensionSpec }>;
  const specs = (): ExtensionSpec[] => {
    const seen = new Set<string>();
    const out: ExtensionSpec[] = [];
    for (const slot of extensionSlots()) {
      if (!seen.has(slot.spec.uri)) {
        seen.add(slot.spec.uri);
        out.push(slot.spec);
      }
    }
    return out;
  };
  const slot = (kind: SlotKind) => slots.find((s) => s.kind === kind);

  const compose = (): GeoIntent => {
    const layers = ((slot("layers")?.get() as LayerRef[] | undefined) ?? []).map((l) => ({ ...l }));
    for (const s of extensionSlots()) {
      if (s.kind !== "layerExtension") continue;
      const byId = (s.get() as Record<string, Record<string, unknown>> | undefined) ?? {};
      for (const layer of layers) {
        const fields = byId[layer.id];
        if (fields) Object.assign(layer, spread(fields, s.spec.name));
      }
    }
    const intent: GeoIntent = {
      geoui_version: PROTOCOL_VERSION,
      geoui_extensions: specs().map((s) => s.uri),
      viewport: (slot("viewport")?.get() as Viewport | undefined) ?? { bbox: null, crs: DEFAULT_CRS },
      time: (slot("time")?.get() as TimeWindow | null | undefined) ?? null,
      layers,
    };
    for (const s of extensionSlots()) {
      if (s.kind !== "extension") continue;
      const fields = s.get() as Record<string, unknown> | null | undefined;
      if (fields) Object.assign(intent, spread(fields, s.spec.name));
    }
    return intent;
  };

  const validate = (input: unknown): ValidateResult => {
    if (!isObject(input)) return fail("invalid_intent", messages.notAnObject());
    if (input.layers !== undefined && !Array.isArray(input.layers)) return fail("invalid_intent", messages.layersNotAList());
    const layers = ((input.layers as unknown[] | undefined) ?? []).filter(isObject);
    if (layers.length !== ((input.layers as unknown[] | undefined) ?? []).length || layers.some((l) => typeof l.id !== "string")) {
      return fail("invalid_intent", messages.layersNotAList());
    }

    const supported = specs().map((s) => s.name);
    const used = new Set<string>([...prefixesIn(input), ...layers.flatMap(prefixesIn)]);
    const unsupported = [...used].filter((p) => !supported.includes(p));
    if (unsupported.length) return fail("unsupported_extension", messages.unsupportedExtension(unsupported, supported));

    for (const spec of specs()) {
      const targets = spec.scope === "intent" ? [input] : layers;
      for (const target of targets) {
        if (!spec.keys.some((k) => k in target)) continue;
        const missing = spec.required.filter((k) => !(k in target));
        if (missing.length) return fail("invalid_intent", messages.missingRequired(spec.name, missing));
      }
    }

    const viewport = normalizeViewport(input.viewport);
    const crs = viewport.crs ?? DEFAULT_CRS;
    if (crs !== DEFAULT_CRS) return fail("unsupported_value", messages.unsupportedCrs(crs));

    if (options.layers?.length) {
      const known = options.layers.map((l) => l.id);
      const referenced = [...layers.map((l) => l.id as string)];
      for (const [key, value] of Object.entries(input)) {
        if (key.endsWith(":layers") && Array.isArray(value)) {
          for (const item of value) if (isObject(item) && typeof item.id === "string") referenced.push(item.id);
        }
      }
      const unknown = [...new Set(referenced.filter((id) => !known.includes(id)))];
      if (unknown.length) return fail("unknown_layer", messages.unknownLayer(unknown, known));
    }

    const intent = { ...input, viewport, layers } as GeoIntent;
    const appError = options.validate?.(intent);
    if (appError) return fail("unsupported_value", appError);
    return { ok: true, intent };
  };

  const nextValue = (s: Slot, intent: GeoIntent, layers: Record<string, unknown>[]): unknown => {
    switch (s.kind) {
      case "viewport":
        return normalizeViewport(intent.viewport);
      case "time":
        return normalizeTime(intent.time);
      case "layers":
        return layers.map(coreLayer);
      case "extension": {
        const fields = prefixed(intent as Record<string, unknown>, s.spec!.name);
        return Object.keys(fields).length ? fields : null;
      }
      case "layerExtension": {
        const byId: Record<string, Record<string, unknown>> = {};
        for (const layer of layers) {
          const fields = prefixed(layer, s.spec!.name);
          if (Object.keys(fields).length) byId[String(layer.id)] = fields;
        }
        return byId;
      }
    }
  };

  const apply = (intent: GeoIntent): boolean => {
    const layers = ((intent.layers as unknown[] | undefined) ?? []).filter(isObject);
    let changed = false;
    for (const s of slots) {
      const value = nextValue(s, intent, layers);
      if (same(s.get(), value)) continue; // no write: React would not re-render anyway
      changed = true;
      s.set(value);
    }
    return changed;
  };

  const settle = (timeoutMs: number): Promise<boolean> =>
    new Promise((resolve) => {
      const timer = setTimeout(() => {
        waiters = waiters.filter((w) => w !== done);
        resolve(false);
      }, timeoutMs);
      const done = (settled: boolean) => {
        clearTimeout(timer);
        resolve(settled);
      };
      waiters.push(done);
    });

  const markSettled = () => {
    const pending = waiters;
    waiters = [];
    for (const w of pending) w(true);
    invalidate();
  };

  const render = async (input: unknown, settleTimeoutMs = DEFAULT_SETTLE_TIMEOUT_MS): Promise<RenderResult> => {
    if (!ready) return fail("not_ready", messages.notReady());
    const checked = validate(input);
    if (!checked.ok) return checked;
    const settling = settle(settleTimeoutMs);
    const changed = apply(checked.intent);
    if (!changed) markSettled(); // nothing will commit; the state already matches
    const settled = await settling;
    return { ok: true, state: compose(), settled };
  };

  return {
    attach(slotToAdd) {
      slots.push(slotToAdd);
      invalidate();
      return () => {
        const i = slots.indexOf(slotToAdd);
        if (i >= 0) slots.splice(i, 1);
        invalidate();
      };
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    snapshot: () => (cached ??= compose()),
    configure: (next) => {
      options = { ...next };
    },
    compose,
    describe: () => ({ version: SDK_VERSION, protocol: PROTOCOL_VERSION, extensions: specs(), layers: options.layers ?? [] }),
    validate,
    apply,
    settle,
    render,
    markReady: () => {
      ready = true;
    },
    markSettled,
    get ready() {
      return ready;
    },
  };
}
