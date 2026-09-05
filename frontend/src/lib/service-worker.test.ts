import { describe, expect, it } from "vitest"
import { NAVIGATE_FALLBACK_DENYLIST, isOutsideAppShell } from "./service-worker"

describe("liste d'exclusion du service worker", () => {
  it("laisse l'API, la supervision, le back-office et les métriques au serveur", () => {
    // Une fois le service worker installé, `/grafana/` s'ouvrait sur
    // l'interface : la navigation hors ligne retombait sur `index.html`.
    for (const chemin of ["/api/me/", "/grafana", "/grafana/", "/grafana/d/abc", "/admin", "/admin/", "/admin/login/", "/metrics"]) {
      expect(isOutsideAppShell(chemin), chemin).toBe(true)
    }
  })

  it("garde les pages de l'application dans le shell", () => {
    for (const chemin of ["/", "/dossiers", "/dossiers/12", "/registre", "/administration", "/metrics-page", "/grafanaX"]) {
      expect(isOutsideAppShell(chemin), chemin).toBe(false)
    }
  })

  it("est celle que le service worker reçoit", () => {
    expect(NAVIGATE_FALLBACK_DENYLIST.map(String)).toEqual([
      String(/^\/api\//),
      String(/^\/grafana(\/|$)/),
      String(/^\/admin(\/|$)/),
      String(/^\/metrics$/),
    ])
  })
})
