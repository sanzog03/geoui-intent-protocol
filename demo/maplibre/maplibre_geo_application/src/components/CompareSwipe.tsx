import type { ViewState, ViewStateChangeEvent } from "react-map-gl/maplibre";
import type { CompareFields, LayerRef } from "@geoui/react-adapter";
import { MapView, type Bbox, type FitRequest } from "./MapView";

export interface CompareSwipeProps {
  viewState: ViewState;
  onMove: (e: ViewStateChangeEvent) => void;
  onBounds: (bbox: Bbox) => void;
  fit: FitRequest | null;
  layersA: LayerRef[];
  dateA: string;
  compare: CompareFields;
  dateFallback: string;
}

/** Two synced maps: A underneath, B clipped to the right of the divider (`compare:value` percent). Spy and opacity modes fall back to swipe. */
export function CompareSwipe({ viewState, onMove, onBounds, fit, layersA, dateA, compare, dateFallback }: CompareSwipeProps) {
  const value = Math.min(100, Math.max(0, compare.value ?? 50));
  const dateB = compare.time?.instant?.slice(0, 10) ?? dateFallback;
  return (
    <>
      <div className="map">
        <MapView viewState={viewState} onMove={onMove} onBounds={onBounds} fit={fit} layers={layersA} date={dateA} />
      </div>
      <div className="map" style={{ clipPath: `inset(0 0 0 ${value}%)` }}>
        <MapView viewState={viewState} controlled onMove={onMove} layers={compare.layers} date={dateB} interactive={false} />
      </div>
      <div className="divider" style={{ left: `${value}%` }} />
      <span className="badge" style={{ left: 8 }}>A · {dateA}</span>
      <span className="badge" style={{ right: 8 }}>B · {dateB}</span>
    </>
  );
}
