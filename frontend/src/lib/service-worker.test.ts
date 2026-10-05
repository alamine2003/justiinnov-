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

  it("laisse les vidéos du guide au serveur, pas la page du guide", () => {
    // Une vidéo ouverte dans un onglet est un fichier : le shell de
    // l'application la remplacerait par l'interface (décision 118).
    expect(isOutsideAppShell("/guides/fr/ouvrir-un-projet.webm")).toBe(true)
    expect(isOutsideAppShell("/guide")).toBe(false)
  })

  it("garde les pages de l'application dans le shell", () => {
    for (const chemin of ["/", "/dossiers", "/dossiers/12", "/registre", "/administration", "/metrics-page", "/grafanaX", "/guide"]) {
      expect(isOutsideAppShell(chemin), chemin).toBe(false)
    }
  })

  it("est celle que le service worker reçoit", () => {
    expect(NAVIGATE_FALLBACK_DENYLIST.map(String)).toEqual([
      String(/^\/api\//),
      String(/^\/grafana(\/|$)/),
      String(/^\/admin(\/|$)/),
      String(/^\/metrics$/),
      String(/^\/guides\//),
    ])
  })
})
