/** NASA GIBS WMTS (Web Mercator "best" endpoint): one tile-URL template per layer and date. */
import type { GibsLayer } from "./layers";

export const GIBS_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";

/** The `{z}/{y}/{x}` template MapLibre needs; static layers use GIBS's `default` time. */
export function tileTemplate(layer: GibsLayer, date: string | null): string {
  const id = layer.gibsId ?? layer.id;
  if (!layer.time) return `${GIBS_BASE}/${id}/default/${layer.matrixSet}/{z}/{y}/{x}.${layer.format}`; // no time dimension
  return `${GIBS_BASE}/${id}/default/${date ?? "default"}/${layer.matrixSet}/{z}/{y}/{x}.${layer.format}`;
}

/** Zoom levels a GoogleMapsCompatible_LevelN matrix set carries (0..N). */
export function maxZoom(layer: GibsLayer): number {
  const match = /Level(\d+)$/.exec(layer.matrixSet);
  return match ? Number(match[1]) : 9;
}
