import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.GUFU_API_URL || "http://127.0.0.1:8000", changeOrigin: true } },
  },
  preview: { port: 4173, proxy: { "/api": { target: process.env.GUFU_API_URL || "http://127.0.0.1:8000", changeOrigin: true } } },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1200 },
});
