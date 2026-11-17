import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": backend,
      "/v1": backend,
      "/health": backend,
      "/metrics": backend,
      "/openapi.json": backend,
      "/docs": backend,
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
