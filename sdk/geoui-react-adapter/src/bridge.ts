/**
 * `window.geoui`: the page-side end of the protocol, what a GeoUI MCP (or any agent host with a
 * handle on the page) calls through `page.evaluate`. `render` never throws; failures come back as
 * `{ok: false, code, error}` so they cross the browser boundary as data.
 */
import type { Catalogue, Registry, RenderResult } from "./registry";
import type { GeoIntent } from "./generated/geo-intent";
import { PROTOCOL_VERSION, SDK_VERSION } from "./version";

export interface GeoUIBridge {
  /** @geoui/react-adapter version. */
  readonly version: string;
  /** GeoUI protocol version (`geoui_version`). */
  readonly protocol: string;
  /** True once the provider has mounted. */
  readonly ready: boolean;
  describe(): Catalogue;
  getState(): GeoIntent;
  render(intent: unknown): Promise<RenderResult>;
}

export const GLOBAL_NAME = "geoui";

type Host = { [GLOBAL_NAME]?: GeoUIBridge };

export function createBridge(registry: Registry, settleTimeoutMs?: number): GeoUIBridge {
  return {
    version: SDK_VERSION,
    protocol: PROTOCOL_VERSION,
    get ready() {
      return registry.ready;
    },
    describe: () => registry.describe(),
    getState: () => registry.compose(),
    render: (intent) => registry.render(intent, settleTimeoutMs),
  };
}

/** Install `window.geoui` (or on `target`); returns the uninstaller. */
export function installBridge(registry: Registry, target: object = globalThis, settleTimeoutMs?: number): () => void {
  const host = target as Host;
  host[GLOBAL_NAME] = createBridge(registry, settleTimeoutMs);
  return () => {
    if (host[GLOBAL_NAME]?.describe !== undefined) delete host[GLOBAL_NAME];
  };
}
