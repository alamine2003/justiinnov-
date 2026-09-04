import path from "path"
/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { VitePWA } from "vite-plugin-pwa"

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const proxyTarget = env.VITE_PROXY_TARGET || "http://localhost:8000"
  return {
    plugins: [
      react(),
      tailwindcss(),
      // Application installable (Chrome et Edge sur Windows et macOS).
      VitePWA({
        registerType: "autoUpdate",
        includeAssets: ["favicon.svg", "favicon.png", "icons/apple-touch-icon.png"],
        manifest: {
          name: "JUSTI INNOV",
          short_name: "JUSTI INNOV",
          description:
            "Contrôle budgétaire des pays : dépenses, justificatifs et enveloppes, en temps réel.",
          lang: "fr",
          display: "standalone",
          start_url: "/",
          scope: "/",
          // Fond de page du thème clair et du thème sombre (`--background`).
          theme_color: "#fafafb",
          background_color: "#fafafb",
          icons: [
            { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
            { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
            {
              src: "/icons/icon-maskable-512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
        },
        workbox: {
          // Précache de l'interface : fichiers hachés par Vite, index.html,
          // icônes et polices.
          globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
          // Une police variable pèse plus que la limite par défaut (2 Mo).
          maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
          // Navigation hors ligne : le shell de l'application, sauf pour
          // l'API, qui n'est jamais servie depuis le cache.
          navigateFallback: "/index.html",
          navigateFallbackDenylist: [/^\/api\//],
          // L'application est temps réel : aucune donnée métier en cache.
          runtimeCaching: [
            {
              urlPattern: ({ url }) => url.pathname.startsWith("/api/"),
              handler: "NetworkOnly",
            },
          ],
          cleanupOutdatedCaches: true,
          clientsClaim: true,
        },
      }),
    ],
    resolve: {
      alias: {
        "@": path.resolve(import.meta.dirname, "./src"),
      },
    },
    server: {
      host: true,
      port: 5173,
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      // Vite 8 s'appuie sur rolldown : le découpage se déclare par groupes
      // plutôt que par `manualChunks`. Les grosses dépendances stables
      // vivent dans leurs propres fichiers, mis en cache indépendamment du
      // code applicatif ; les pages sont chargées à la demande (`React.lazy`).
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              { name: "react", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
              { name: "router", test: /node_modules[\\/]react-router/ },
              { name: "base-ui", test: /node_modules[\\/]@base-ui[\\/]/ },
              { name: "axios", test: /node_modules[\\/]axios[\\/]/ },
              { name: "i18n", test: /node_modules[\\/](i18next|react-i18next|i18next-browser-languagedetector)[\\/]/ },
            ],
          },
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
      // Les captures Playwright ne sont pas des tests unitaires.
      include: ["src/**/*.test.{ts,tsx}"],
    },
  }
})
