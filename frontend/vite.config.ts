import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The SPA talks to the backend through a dev proxy so no CORS config is needed
// on Django. In Docker Compose VITE_API_PROXY_TARGET is http://backend:8000;
// running Vite on the host it defaults to http://localhost:8000.
export default defineConfig(() => {
  const proxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";
  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
      host: true,
      port: Number(process.env.FRONTEND_PORT ?? 5173),
      proxy: {
        "/api": { target: proxyTarget, changeOrigin: true },
      },
    },
  };
});
