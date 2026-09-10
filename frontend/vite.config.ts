import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// The SPA talks to the backend through a dev proxy so no CORS config is needed
// on Django. In Docker Compose VITE_API_PROXY_TARGET is http://backend:8000;
// running Vite on the host it defaults to http://localhost:8000.
export default defineConfig(() => {
  const proxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";
  return {
    plugins: [
      react(),
      // Phase 6: installable PWA for the mobile barcode scanner. The service
      // worker precaches the built app shell only — API and media requests are
      // always network-only so authed data is never served stale/offline.
      VitePWA({
        registerType: "autoUpdate",
        injectRegister: "auto",
        includeAssets: ["favicon.ico", "apple-touch-icon.png"],
        manifest: {
          name: "Hexagare",
          short_name: "Hexagare",
          description: "Product, inventory and billing — with a mobile barcode scanner.",
          start_url: "/",
          scope: "/",
          display: "standalone",
          orientation: "portrait",
          background_color: "#0f172a",
          theme_color: "#0f172a",
          icons: [
            { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
            { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
            {
              src: "pwa-maskable-512x512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
        },
        workbox: {
          globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
          navigateFallback: "/index.html",
          // Never let the SW answer for the API or uploaded media.
          navigateFallbackDenylist: [/^\/api\//, /^\/media\//],
          runtimeCaching: [
            {
              urlPattern: ({ url }) =>
                url.pathname.startsWith("/api/") || url.pathname.startsWith("/media/"),
              handler: "NetworkOnly",
            },
          ],
        },
        devOptions: {
          // Keep the SW out of `npm run dev` — it only complicates hot reload.
          enabled: false,
        },
      }),
    ],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
      host: true,
      port: Number(process.env.FRONTEND_PORT ?? 5173),
      proxy: {
        "/api": { target: proxyTarget, changeOrigin: true },
        // Serialized image URLs are root-relative (/media/...); forward them to
        // the backend, which serves uploaded files in development.
        "/media": { target: proxyTarget, changeOrigin: true },
      },
    },
  };
});
