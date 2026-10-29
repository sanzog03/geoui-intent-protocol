import type { CompareFields, LayerRef, RasterStylingFields } from "@geoui/react-adapter";
import { LAYERS } from "../layers";

export interface ControlsProps {
  date: string;
  setDate: (d: string) => void;
  layers: LayerRef[];
  setLayers: (l: LayerRef[]) => void;
  compare: CompareFields | null;
  setCompare: (c: CompareFields | null) => void;
  styling: Record<string, RasterStylingFields>;
}

/** The app's own UI: the same state the agent drives, so hand edits and agent edits are one thing. */
export function Controls({ date, setDate, layers, setLayers, compare, setCompare, styling }: ControlsProps) {
  const active = new Map(layers.map((l) => [l.id, l]));
  const toggle = (id: string, on: boolean) => {
    if (on) setLayers([...layers.filter((l) => l.id !== id), { id, visible: true, opacity: null }]);
    else setLayers(layers.filter((l) => l.id !== id));
  };
  const opacity = (id: string, value: number) => setLayers(layers.map((l) => (l.id === id ? { ...l, opacity: value } : l)));

  return (
    <div className="panel">
      <h1>GeoUI MapLibre demo</h1>
      <p className="muted">
        A plain React map whose state is attached to the GeoUI protocol with <code>@geoui/react-adapter</code>. Change it here, or let an agent change it through <code>window.geoui</code>.
      </p>
      <h2>Date</h2>
      <input id="date" type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
      <h2>Layers (bottom first)</h2>
      {LAYERS.map((def) => {
        const l = active.get(def.id);
        return (
          <div className="layer" key={def.id}>
            <input id={`layer-${def.id}`} type="checkbox" checked={Boolean(l)} onChange={(e) => toggle(def.id, e.target.checked)} />
            <label htmlFor={`layer-${def.id}`} title={def.id}>
              {def.title}
              {styling[def.id] ? <span className="muted"> · styled {JSON.stringify(styling[def.id])}</span> : null}
            </label>
            <input type="range" min={0} max={1} step={0.05} value={l?.opacity ?? 1} disabled={!l} onChange={(e) => opacity(def.id, Number(e.target.value))} title="opacity" />
          </div>
        );
      })}
      <h2>Compare</h2>
      <label>
        <input id="compare-on" type="checkbox" checked={compare !== null} onChange={(e) => setCompare(e.target.checked ? { layers: [layers[0] ?? { id: LAYERS[0]!.id }], mode: "swipe", value: 50 } : null)} /> swipe against a second view
      </label>
      {compare ? (
        <>
          <label>
            B layer{" "}
            <select id="compare-layer" value={compare.layers[0]?.id} onChange={(e) => setCompare({ ...compare, layers: [{ id: e.target.value }] })}>
              {LAYERS.map((def) => (
                <option key={def.id} value={def.id}>
                  {def.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            B date <input id="compare-date" type="date" value={compare.time?.instant?.slice(0, 10) ?? date} onChange={(e) => setCompare({ ...compare, time: e.target.value ? { instant: e.target.value } : null })} />
          </label>
          <label>
            divider <input id="compare-value" type="range" min={0} max={100} value={compare.value ?? 50} onChange={(e) => setCompare({ ...compare, value: Number(e.target.value) })} />
          </label>
        </>
      ) : null}
    </div>
  );
}
