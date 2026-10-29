import { useEffect, useState } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import Map, { Layer, Source, type MapEvent, type ViewState, type ViewStateChangeEvent } from "react-map-gl/maplibre";
import type { LayerRef } from "@geoui/react-adapter";
import { maxZoom, tileTemplate } from "../gibs";
import { LAYER_BY_ID } from "../layers";

export type Bbox = [number, number, number, number];

/** A request to fit the map to a bbox; `seq` makes repeated fits to the same bbox distinct. */
export interface FitRequest {
  bbox: Bbox;
  seq: number;
}

export interface MapViewProps {
  viewState: ViewState;
  /**
   * A controlled map follows `viewState` exactly (the compare B side, which mirrors A). The primary map
   * is uncontrolled: it starts from `viewState` and is moved by the user or by `fit`. react-map-gl
   * reverts an imperative fitBounds on a controlled map until the props catch up, one render late.
   */
  controlled?: boolean;
  onMove: (e: ViewStateChangeEvent) => void;
  /** Called with the map's exact bounds after every move (including fits). */
  onBounds?: (bbox: Bbox) => void;
  fit?: FitRequest | null;
  layers: LayerRef[];
  date: string;
  interactive?: boolean;
}

const EMPTY_STYLE = { version: 8 as const, sources: {}, layers: [] };

export function boundsOf(map: MapLibreMap): Bbox {
  const b = map.getBounds();
  const r = (n: number) => Math.round(n * 10_000) / 10_000;
  return [r(b.getWest()), r(b.getSouth()), r(b.getEast()), r(b.getNorth())];
}

/** One MapLibre map showing a GeoIntent layer stack (bottom first) for one date. */
export function MapView({ viewState, controlled = false, onMove, onBounds, fit, layers, date, interactive = true }: MapViewProps) {
  const [map, setMap] = useState<MapLibreMap | null>(null);

  // Apply a fit once the map exists (a fresh map instance after a compare toggle included).
  useEffect(() => {
    if (!map || !fit) return;
    const [w, s, e, n] = fit.bbox;
    map.fitBounds([[w, s], [e, n]], { duration: 0 });
  }, [map, fit]);

  return (
    <Map
      {...(controlled ? viewState : { initialViewState: viewState })}
      onLoad={(e: MapEvent) => setMap(e.target)}
      onMove={onMove}
      onMoveEnd={(e) => onBounds?.(boundsOf(e.target))}
      mapStyle={EMPTY_STYLE}
      interactive={interactive}
      style={{ width: "100%", height: "100%", background: "#0b1d2a" }}
      attributionControl={false}
      renderWorldCopies={false}
    >
      {layers
        .filter((l) => l.visible !== false && LAYER_BY_ID[l.id])
        .map((l) => {
          const def = LAYER_BY_ID[l.id]!;
          const key = `${l.id}@${def.time ? date : "static"}`;
          return (
            <Source key={key} id={key} type="raster" tiles={[tileTemplate(def, date)]} tileSize={256} maxzoom={maxZoom(def)}>
              <Layer id={`${key}-layer`} type="raster" paint={{ "raster-opacity": l.opacity ?? 1, "raster-fade-duration": 0 }} />
            </Source>
          );
        })}
    </Map>
  );
}
