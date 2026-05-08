import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// CustDevAI веб-панель управления (FR-WEB-01..12).
// dev-режим: Vite dev server :5173 с HMR; API на :8000 с CORS.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: "0.0.0.0",
    strictPort: true,
  },
  preview: {
    port: 5173,
  },
});
