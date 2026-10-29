/**
 * Attach hooks: the app passes its own state and setter for one protocol field (or one
 * extension) and the SDK gains read and write access to it. The value is read through a ref
 * synced after every commit, so `getState()` always sees the committed value; the setter is
 * called from `render()`. Every hook also signals a commit, which is what `render()` waits for.
 */
import { useEffect, useLayoutEffect, useRef } from "react";
import type { ExtensionSpec } from "./extensions";
import type { LayerRef, TimeWindow, Viewport } from "./generated/geo-intent";
import { useGeoUIRegistry } from "./provider";
import type { SlotKind } from "./registry";

function useSlot<T>(kind: SlotKind, spec: ExtensionSpec<unknown> | undefined, value: T, setValue: (v: T) => void): void {
  const registry = useGeoUIRegistry();
  const valueRef = useRef(value);
  const setRef = useRef(setValue);

  useLayoutEffect(() => {
    valueRef.current = value;
    setRef.current = setValue;
  });

  useLayoutEffect(
    () => registry.attach({ kind, spec, get: () => valueRef.current, set: (v) => setRef.current(v as T) }),
    [registry, kind, spec],
  );

  // After every commit of the host component: whatever `render()` applied is now on screen.
  useEffect(() => {
    registry.markSettled();
  });
}

/** Attach the spatial viewport (`bbox` as [west, south, east, north] in `crs`, EPSG:4326 by default). */
export function useGeoUIViewport(value: Viewport, setValue: (v: Viewport) => void): void {
  useSlot("viewport", undefined, value, setValue);
}

/** Attach the time selection (`{instant}` or `{start, end}`; null means the app default). */
export function useGeoUITime(value: TimeWindow | null, setValue: (v: TimeWindow | null) => void): void {
  useSlot("time", undefined, value, setValue);
}

/** Attach the layer stack (core fields only: id, visible, opacity). */
export function useGeoUILayers(value: LayerRef[], setValue: (v: LayerRef[]) => void): void {
  useSlot("layers", undefined, value, setValue);
}

/** Attach an intent-scoped extension (e.g. `extensions.compare`); null means "not in use". */
export function useGeoUIExtension<F>(spec: ExtensionSpec<F>, value: F | null, setValue: (v: F | null) => void): void {
  if (spec.scope !== "intent") throw new Error(`${spec.name} is a layer-scoped extension; use useGeoUILayerExtension`);
  useSlot("extension", spec, value, setValue);
}

/** Attach a layer-scoped extension (e.g. `extensions.rasterStyling`): fields per layer id. */
export function useGeoUILayerExtension<F>(spec: ExtensionSpec<F>, value: Record<string, F>, setValue: (v: Record<string, F>) => void): void {
  if (spec.scope !== "layer") throw new Error(`${spec.name} is an intent-scoped extension; use useGeoUIExtension`);
  useSlot("layerExtension", spec, value, setValue);
}
