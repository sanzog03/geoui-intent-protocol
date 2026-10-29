import { useGeoUIBridge, useGeoUIState } from "@geoui/react";

/** What an agent reads right now: window.geoui.getState(), live. */
export function StatePanel() {
  const state = useGeoUIState();
  const bridge = useGeoUIBridge();
  const catalogue = bridge.describe();
  return (
    <div className="panel state">
      <h2>window.geoui.getState()</h2>
      <pre id="state-json">{JSON.stringify(state, null, 2)}</pre>
      <h2>window.geoui.describe()</h2>
      <p className="muted">
        SDK {catalogue.version} · protocol {catalogue.protocol} · extensions: {catalogue.extensions.map((e) => e.name).join(", ") || "none"} · {catalogue.layers.length} layers
      </p>
      <p className="muted">
        Drive it from Python: <code>uv run geoui-bridge-mcp</code> with <code>GEOUI_APP_URL={location.origin}</code>, or from the console: <code>await geoui.render({"{"}layers: [{"{"}id: "Coastlines_15m"{"}"}]{"}"})</code>.
      </p>
    </div>
  );
}
