/**
 * `GeoUIProvider` owns one registry for the React tree below it, installs `window.geoui` and
 * marks the registry ready once the children have attached their slots. The app keeps its own
 * state; the attach hooks in ./hooks.ts register getters and setters for it.
 */
import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { createBridge, installBridge, type GeoUIBridge } from "./bridge";
import type { GeoIntent } from "./generated/geo-intent";
import { createRegistry, DEFAULT_SETTLE_TIMEOUT_MS, type Registry, type RegistryOptions } from "./registry";

export interface GeoUIProviderProps extends RegistryOptions {
  /** How long `render()` waits for a React commit before answering with `settled: false`. */
  settleTimeoutMs?: number;
  /** Expose `window.geoui` (default true). Set false to drive the registry yourself. */
  install?: boolean;
  children: ReactNode;
}

const RegistryContext = createContext<Registry | null>(null);

export function GeoUIProvider({ layers, validate, settleTimeoutMs = DEFAULT_SETTLE_TIMEOUT_MS, install = true, children }: GeoUIProviderProps) {
  const [registry] = useState(() => createRegistry({ layers, validate }));

  useLayoutEffect(() => {
    registry.configure({ layers, validate });
  }, [registry, layers, validate]);

  useLayoutEffect(() => {
    if (!install) return undefined;
    return installBridge(registry, globalThis, settleTimeoutMs);
  }, [registry, install, settleTimeoutMs]);

  // Children's layout effects (slot attachment) run before this passive effect.
  useEffect(() => {
    registry.markReady();
  }, [registry]);

  return <RegistryContext.Provider value={registry}>{children}</RegistryContext.Provider>;
}

export function useGeoUIRegistry(): Registry {
  const registry = useContext(RegistryContext);
  if (!registry) throw new Error("GeoUI hooks must be used inside <GeoUIProvider>");
  return registry;
}

/** The same object `window.geoui` exposes, for the app's own UI (a state panel, a debug view). */
export function useGeoUIBridge(): GeoUIBridge {
  const registry = useGeoUIRegistry();
  return useMemo(() => createBridge(registry), [registry]);
}

/** The composed GeoIntent, re-rendering after every commit: what an agent would read right now. */
export function useGeoUIState(): GeoIntent {
  const registry = useGeoUIRegistry();
  return useSyncExternalStore(registry.subscribe, registry.snapshot, registry.snapshot);
}
