import path from "path"
/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const proxyTarget = env.VITE_PROXY_TARGET || "http://localhost:8000"
  return {
    plugins: [react(), tailwindcss()],
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
