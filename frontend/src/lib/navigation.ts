/**
 * Écran auquel une page « appartient » : la liste de sa section.
 *
 * `/dossiers/12` → `/dossiers`, `/countries/3` → `/countries`, et une
 * section elle-même (`/dossiers`, `/configuration`…) → l'accueil. Sert de
 * repli au bouton « Retour » quand la navigation n'a pas commencé dans
 * l'application (`components/layout/back-button.tsx`).
 */
export function parentPath(pathname: string): string {
  const segments = pathname.split("/").filter(Boolean)
  if (segments.length <= 1) return "/"
  return `/${segments.slice(0, -1).join("/")}`
}
