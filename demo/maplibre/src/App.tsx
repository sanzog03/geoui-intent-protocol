/**
 * The app owns its state (view, date, layer stack, compare, styling) and attaches each piece to the
 * GeoUI protocol with the @geoui/react hooks. Nothing else knows about agents.
 */
import { useCallback, useState } from "react";
import type { ViewState, ViewStateChangeEvent } from "react-map-gl/maplibre";
import { extensions, useGeoUIExtension, useGeoUILayerExtension, useGeoUILayers, useGeoUITime, useGeoUIViewport } from "@geoui/react";
import type { CompareFields, LayerRef, RasterStylingFields, TimeWindow, Viewport } from "@geoui/react";
import { CompareSwipe } from "./components/CompareSwipe";
import { Controls } from "./components/Controls";
import { MapView, type Bbox, type FitRequest } from "./components/MapView";
import { StatePanel } from "./components/StatePanel";
import { DEFAULT_DATE, DEFAULT_LAYERS } from "./layers";

const CONUS: Viewport = { bbox: [-125, 24, -66, 50], crs: "EPSG:4326" };
const INITIAL_VIEW: ViewState = { longitude: -96, latitude: 38, zoom: 3, bearing: 0, pitch: 0, padding: { top: 0, bottom: 0, left: 0, right: 0 } };

export function App() {
  const [viewState, setViewState] = useState<ViewState>(INITIAL_VIEW);
  const [viewport, setViewportState] = useState<Viewport>(CONUS);
  const [time, setTimeState] = useState<TimeWindow | null>({ instant: DEFAULT_DATE });
  const [layers, setLayers] = useState<LayerRef[]>(DEFAULT_LAYERS.map((id) => ({ id, visible: true, opacity: null })));
  const [compare, setCompare] = useState<CompareFields | null>(null);
  const [styling, setStyling] = useState<Record<string, RasterStylingFields>>({});

  const date = time?.instant?.slice(0, 10) ?? DEFAULT_DATE;

  // The map is the source of truth for the viewport: a render asks for a fit, the mounted map applies it
  // once it exists (compare may swap the map instance in the same render), and the map's own move-end
  // writes the exact bounds back, so the reported state is what is on screen.
  const [fit, setFit] = useState<FitRequest | null>({ bbox: CONUS.bbox as Bbox, seq: 1 });
  const setViewport = useCallback((v: Viewport) => {
    const target = (v.bbox ?? CONUS.bbox) as Bbox;
    setViewportState({ bbox: target, crs: "EPSG:4326" });
    setFit((f) => ({ bbox: target, seq: (f?.seq ?? 0) + 1 }));
  }, []);
  const onMove = useCallback((e: ViewStateChangeEvent) => setViewState(e.viewState), []);
  const onBounds = useCallback((bbox: Bbox) => setViewportState({ bbox, crs: "EPSG:4326" }), []);

  // Agents write time as an instant; a null (app default) becomes the default date so the state stays concrete.
  const setTime = useCallback((t: TimeWindow | null) => setTimeState(t?.instant ? { instant: t.instant.slice(0, 10) } : { instant: DEFAULT_DATE }), []);
  const setDate = (d: string) => setTimeState({ instant: d });

  useGeoUIViewport(viewport, setViewport);
  useGeoUITime(time, setTime);
  useGeoUILayers(layers, setLayers);
  useGeoUIExtension(extensions.compare, compare, setCompare);
  useGeoUILayerExtension(extensions.rasterStyling, styling, setStyling);

  return (
    <div className="app">
      <Controls date={date} setDate={setDate} layers={layers} setLayers={setLayers} compare={compare} setCompare={setCompare} styling={styling} />
      <div className="map-area">
        {compare ? (
          <CompareSwipe viewState={viewState} onMove={onMove} onBounds={onBounds} fit={fit} layersA={layers} dateA={date} compare={compare} dateFallback={date} />
        ) : (
          <div className="map">
            <MapView viewState={viewState} onMove={onMove} onBounds={onBounds} fit={fit} layers={layers} date={date} />
          </div>
        )}
      </div>
      <StatePanel />
    </div>
  );
}
