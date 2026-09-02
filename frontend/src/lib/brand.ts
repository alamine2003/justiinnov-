/**
 * Identité de l'application.
 *
 * Rassemblée ici pour que le nom, la version et l'auteur ne soient écrits
 * qu'une fois : les recopier dans l'en-tête, le pied de page et le titre de
 * l'onglet les ferait diverger dès la première mise à jour.
 */
export const BRAND = {
  name: "JUSTI INNOV",
  tagline: "Application de contrôle budgétaire",
  version: "1.0",
  developer: "Al Amine DEV",
  /** Année de première mise en service, pour la mention de copyright. */
  since: 2026,
  logo: "/justi-innov.png",
  mark: "/justi-innov-mark.png",
} as const

/** Mention de copyright, l'année courante si elle dépasse la mise en service. */
export function copyright(): string {
  const année = new Date().getFullYear()
  const période =
    année > BRAND.since ? `${BRAND.since}–${année}` : `${BRAND.since}`
  return `© ${période} ${BRAND.name}. Tous droits réservés.`
}
