import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import "./index.css"
import "./i18n"
import App from "./App.tsx"
import { OfflineNotice } from "./components/layout/offline-notice"
import { AuthProvider } from "./context/auth"
import { ThemeProvider } from "./context/theme"
import { captureInstallPrompt } from "./lib/install-prompt"
import { registerServiceWorker } from "./pwa"

// Avant le premier rendu : l'événement d'installation peut partir avant que
// React soit monté.
captureInstallPrompt()
registerServiceWorker()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <OfflineNotice />
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)
