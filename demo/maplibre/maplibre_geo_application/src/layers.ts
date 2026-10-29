/**
 * The layer catalogue: what this app can show, published to agents through window.geoui.describe().
 * Ids are GIBS layer identifiers, so they coincide with NASA Worldview's; the matrix set and format
 * are what the epsg3857 "best" endpoint serves for each product.
 */
import type { LayerCatalogueEntry } from "@geoui/react-adapter";

export interface GibsLayer extends LayerCatalogueEntry {
  matrixSet: string;
  format: "jpg" | "png";
  /** GIBS identifier when it differs from the catalogue id (Worldview names a few products differently). */
  gibsId?: string;
  /** Rendered beneath everything else when nothing else is visible: a basemap. */
  base?: boolean;
}

const daily = (start: string) => ({ start, end: null, period: "P1D" });

export const LAYERS: GibsLayer[] = [
  { id: "MODIS_Terra_CorrectedReflectance_TrueColor", title: "MODIS Terra corrected reflectance (true color)", time: daily("2000-02-24"), matrixSet: "GoogleMapsCompatible_Level9", format: "jpg", base: true },
  { id: "MODIS_Aqua_CorrectedReflectance_TrueColor", title: "MODIS Aqua corrected reflectance (true color)", time: daily("2002-07-04"), matrixSet: "GoogleMapsCompatible_Level9", format: "jpg", base: true },
  { id: "VIIRS_SNPP_CorrectedReflectance_TrueColor", title: "VIIRS SNPP corrected reflectance (true color)", time: daily("2015-11-24"), matrixSet: "GoogleMapsCompatible_Level9", format: "jpg", base: true },
  { id: "MODIS_Aqua_Aerosol_Optical_Depth_3km", title: "MODIS Aqua aerosol optical depth, 3 km", time: daily("2002-07-04"), matrixSet: "GoogleMapsCompatible_Level6", format: "png" },
  { id: "MODIS_Terra_Aerosol_Optical_Depth_3km", title: "MODIS Terra aerosol optical depth, 3 km", time: daily("2000-02-24"), matrixSet: "GoogleMapsCompatible_Level6", format: "png" },
  { id: "AIRS_L3_Surface_Air_Temperature_Daily_Day_Mean", title: "AIRS surface air temperature, daily day mean", time: daily("2002-09-01"), matrixSet: "GoogleMapsCompatible_Level6", format: "png", gibsId: "AIRS_L3_Surface_Air_Temperature_Daily_Day" },
  { id: "AIRS_L3_Surface_Air_Temperature_Daily_Night_Mean", title: "AIRS surface air temperature, daily night mean", time: daily("2002-09-01"), matrixSet: "GoogleMapsCompatible_Level6", format: "png", gibsId: "AIRS_L3_Surface_Air_Temperature_Daily_Night" },
  { id: "GHRSST_L4_MUR_Sea_Surface_Temperature", title: "GHRSST MUR sea surface temperature", time: daily("2002-06-01"), matrixSet: "GoogleMapsCompatible_Level7", format: "png" },
  { id: "GHRSST_L4_MUR_Sea_Surface_Temperature_Anomalies", title: "GHRSST MUR sea surface temperature anomalies", time: daily("2002-06-01"), matrixSet: "GoogleMapsCompatible_Level7", format: "png" },
  { id: "MODIS_Terra_Land_Surface_Temp_Day", title: "MODIS Terra land surface temperature (day)", time: daily("2000-02-24"), matrixSet: "GoogleMapsCompatible_Level7", format: "png" },
  { id: "Coastlines_15m", title: "Coastlines", matrixSet: "GoogleMapsCompatible_Level13", format: "png" },
  { id: "Reference_Features_15m", title: "Reference features (borders, roads)", matrixSet: "GoogleMapsCompatible_Level13", format: "png" },
  { id: "Reference_Labels_15m", title: "Reference labels (place names)", matrixSet: "GoogleMapsCompatible_Level13", format: "png" },
];

export const LAYER_BY_ID: Record<string, GibsLayer> = Object.fromEntries(LAYERS.map((l) => [l.id, l]));

/** What describe() publishes: the catalogue entries without the rendering details. */
export const CATALOGUE: LayerCatalogueEntry[] = LAYERS.map(({ id, title, time }) => (time ? { id, title, time } : { id, title }));

export const DEFAULT_DATE = "2025-09-15";
export const DEFAULT_LAYERS = ["MODIS_Terra_CorrectedReflectance_TrueColor", "Coastlines_15m"];
