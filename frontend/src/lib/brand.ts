import i18next from "i18next"

/**
 * Identité de l'application.
 *
 * Rassemblée ici pour que le nom, la version et l'auteur ne soient écrits
 * qu'une fois : les recopier dans l'en-tête, le pied de page et le titre de
 * l'onglet les ferait diverger dès la première mise à jour.
 *
 * La version n'est pas écrite ici : elle est figée à la construction
 * (`__APP_VERSION__`, `vite.config.ts`) — celle du tag `v*` livré, posée
 * par la CI dans l'image, sinon celle de `package.json`. Poser un tag
 * suffit à la faire changer ; personne n'a à l'écrire deux fois.
 */
export const BRAND = {
  name: "JUSTI GH",
  /** Le mot écrit dans le logo, avant le monogramme « GH » qui achève le nom. */
  mot: "JUSTI",
  /** La signature (« Application de contrôle budgétaire ») est traduite : clé `app.tagline`. */
  version: __APP_VERSION__,
  developer: "Al Amine dev",
  /** Année de première mise en service, pour la mention de copyright. */
  since: 2026,
} as const

// L'emblème et le logo sont des composants (`components/layout/brand-mark.tsx`,
// `brand-logo.tsx`) : le monogramme de Generic Healthcare vectorisé depuis
// `docs/identite/logo-gh.png`, le mot écrit en texte (décision 92) ;
// l'icône d'onglet et d'application installée — le monogramme sur un carré
// blanc — vit dans `public/favicon.svg` et `public/icons/`.

/** Mention de copyright, l'année courante si elle dépasse la mise en service. */
export function copyright(): string {
  const annee = new Date().getFullYear()
  const periode =
    annee > BRAND.since ? `${BRAND.since}–${annee}` : `${BRAND.since}`
  return i18next.t("layout.copyright", { periode, nom: BRAND.name })
}
