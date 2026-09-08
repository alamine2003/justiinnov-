import i18next from "i18next"

/**
 * Identité de l'application.
 *
 * Rassemblée ici pour que le nom, la version et l'auteur ne soient écrits
 * qu'une fois : les recopier dans l'en-tête, le pied de page et le titre de
 * l'onglet les ferait diverger dès la première mise à jour.
 */
export const BRAND = {
  name: "JUSTI INNOV",
  /** La signature (« Application de contrôle budgétaire ») est traduite : clé `app.tagline`. */
  version: "1.0.0",
  developer: "Al Amine DEV",
  /** Année de première mise en service, pour la mention de copyright. */
  since: 2026,
  /**
   * Emblème de la marque, celui de l'onglet du navigateur : un seul fichier
   * d'identité servi, pour que l'en-tête, la page de connexion et l'onglet ne
   * puissent pas montrer trois logos différents. Il n'est pas vectoriel — le
   * logo n'existe qu'en image —, mais il n'est jamais affiché au-delà de
   * 44 px (`app-layout.tsx`, `login.tsx`), où 64 px suffisent.
   */
  mark: "/favicon.png",
} as const

/** Mention de copyright, l'année courante si elle dépasse la mise en service. */
export function copyright(): string {
  const annee = new Date().getFullYear()
  const periode =
    annee > BRAND.since ? `${BRAND.since}–${annee}` : `${BRAND.since}`
  return i18next.t("layout.copyright", { periode, nom: BRAND.name })
}
