/**
 * Chemins que le service worker ne doit jamais servir depuis le shell de
 * l'application (`index.html`) quand une navigation échoue hors ligne :
 *
 * - `/api/` : jamais un chiffre périmé, l'API passe toujours par le réseau ;
 * - `/grafana` : la supervision a sa propre application, servie par Caddy ;
 * - `/admin` : le back-office Django ;
 * - `/metrics` : l'exposition Prometheus ;
 * - `/guides/` : les vidéos du guide (décision 118), servies telles quelles
 *   et jamais mises en cache — une vidéo ouverte dans un onglet est un
 *   fichier, pas une page de l'application.
 *
 * Sans cette liste, ouvrir `/grafana/` dans un nouvel onglet affichait
 * l'interface au lieu de la supervision, une fois le service worker installé.
 */
export const NAVIGATE_FALLBACK_DENYLIST: RegExp[] = [
  /^\/api\//,
  /^\/grafana(\/|$)/,
  /^\/admin(\/|$)/,
  /^\/metrics$/,
  /^\/guides\//,
]

/** Vrai si le chemin est laissé au serveur plutôt qu'au shell de l'application. */
export function isOutsideAppShell(pathname: string): boolean {
  return NAVIGATE_FALLBACK_DENYLIST.some((pattern) => pattern.test(pathname))
}
