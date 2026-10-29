/**
 * The shipped extension specs, exactly as `geoui.extensions.<name>.SPEC.describe()` lays them out in Python
 * (the JSON under schemas/extensions, embedded by scripts/gen-types.ts). An app attaches the ones it
 * implements; the agent sees that list through window.geoui.describe().
 */
import type { ChartFields, CompareFields, RasterStylingFields } from "./generated/geo-intent";
import { CHART_SPEC, COMPARE_SPEC, RASTER_STYLING_SPEC } from "./generated/schemas";

/** One extension: its URI, key prefix, where its fields live, and their JSON Schema. `F` is the fields' TypeScript shape. */
export interface ExtensionSpec<F = unknown> {
  readonly name: string;
  readonly uri: string;
  /** "intent": namespaced keys on the GeoIntent root; "layer": namespaced keys on each LayerRef. */
  readonly scope: "intent" | "layer";
  readonly summary: string;
  /** The namespaced keys a producer writes, e.g. `compare:layers`. */
  readonly keys: readonly string[];
  /** Keys that must be present once the extension is used. */
  readonly required: readonly string[];
  readonly fields_schema: Record<string, unknown>;
  /** Phantom: carries `F` for typing only; never set at runtime. */
  readonly __fields?: F;
}

export const extensions = {
  compare: COMPARE_SPEC as unknown as ExtensionSpec<CompareFields>,
  chart: CHART_SPEC as unknown as ExtensionSpec<ChartFields>,
  rasterStyling: RASTER_STYLING_SPEC as unknown as ExtensionSpec<RasterStylingFields>,
} as const;
