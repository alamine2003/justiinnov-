import { registerSW } from "virtual:pwa-register"

/**
 * Enregistre le service worker de l'application installable.
 *
 * Mode `autoUpdate` : une nouvelle version livrée remplace la précédente au
 * prochain chargement, sans demander. Rien de métier n'est mis en cache — les
 * appels `/api/` passent toujours par le réseau —, seule l'interface l'est.
 */
export function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return
  registerSW({ immediate: true })
}
