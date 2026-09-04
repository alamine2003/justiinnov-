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
  /** Emblème vectoriel : net à toute taille, et le seul fichier d'identité servi. */
  mark: "/favicon.svg",
} as const

/** Mention de copyright, l'année courante si elle dépasse la mise en service. */
export function copyright(): string {
  const annee = new Date().getFullYear()
  const periode =
    annee > BRAND.since ? `${BRAND.since}–${annee}` : `${BRAND.since}`
  return i18next.t("layout.copyright", { periode, nom: BRAND.name })
}
