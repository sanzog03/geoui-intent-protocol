/**
 * Render error codes and their messages. The wording mirrors the Python tool layer
 * (`worldview.tools.prepare_intent`) so an agent sees the same guidance from either side.
 */

export type RenderErrorCode = "not_ready" | "invalid_intent" | "unsupported_extension" | "unknown_layer" | "unsupported_value";

export interface RenderError {
  ok: false;
  code: RenderErrorCode;
  error: string;
}

export function fail(code: RenderErrorCode, error: string): RenderError {
  return { ok: false, code, error };
}

/** `['a', 'b']`, the way Python prints a list of strings. */
function pyList(items: readonly string[]): string {
  return `[${items.map((s) => `'${s}'`).join(", ")}]`;
}

export const messages = {
  notReady: () => "the GeoUI provider is not mounted yet",
  notAnObject: () => "intent is not an object",
  layersNotAList: () => "layers must be a list of {id, visible?, opacity?}",
  unsupportedExtension: (unsupported: readonly string[], supported: readonly string[]) =>
    `extension(s) ${pyList(unsupported)} are not available in this app; supported: ${supported.join(", ")} (see geo_ui_list_intent_extensions_tool)`,
  missingRequired: (prefix: string, missing: readonly string[]) => `extension ${prefix} requires ${missing.join(", ")}`,
  unsupportedCrs: (crs: string) => `viewport.crs '${crs}' is not supported by this app; use EPSG:4326`,
  unknownLayer: (unknown: readonly string[], known: readonly string[]) =>
    `unknown layer id(s) ${pyList(unknown)}; known ids: ${known.slice(0, 20).join(", ")}${known.length > 20 ? ", ..." : ""} (see geo_ui_list_intent_extensions_tool)`,
};
