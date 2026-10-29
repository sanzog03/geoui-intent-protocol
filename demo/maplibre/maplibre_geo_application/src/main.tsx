import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { GeoUIProvider } from "@geoui/react-adapter";
import { App } from "./App";
import { CATALOGUE } from "./layers";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <GeoUIProvider layers={CATALOGUE}>
      <App />
    </GeoUIProvider>
  </StrictMode>,
);
