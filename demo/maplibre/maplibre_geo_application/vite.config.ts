import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The SDK is consumed from source so `npm run dev` needs no prebuild and edits hot-reload.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@geoui/react-adapter": fileURLToPath(new URL("../../../sdk/geoui-react-adapter/src/index.ts", import.meta.url)) } },
  server: { host: "127.0.0.1" },
});
