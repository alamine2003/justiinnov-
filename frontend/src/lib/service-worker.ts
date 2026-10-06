/**
 * Chemins que le service worker ne doit jamais servir depuis le shell de
 * l'application (`index.html`) quand une navigation échoue hors ligne :
 *
 * - `/api/` : jamais un chiffre périmé, l'API passe toujours par le réseau ;
 * - `/grafana` : la supervision a sa propre application, servie par Caddy ;
 * - `/admin` : le back-office Django ;
 * - `/metrics` : l'exposition Prometheus ;
 * - `/guides/` : les fichiers du guide vidéo (décision 118) — une vidéo
 *   ouverte dans un onglet est un fichier, pas une page de l'application.
 *
 * Cette liste ne règle que le repli de navigation : elle n'empêche aucune
 * mise en cache. Si les vidéos, sous-titres et affiches du guide ne sont pas
 * préchargés, c'est que les `globPatterns` de `vite.config.ts` ne retiennent
 * ni `webm`, ni `vtt`, ni `jpg` ; y ajouter l'une de ces extensions ferait
 * précharger les guides à chaque installation, quoi que dise cette liste.
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
