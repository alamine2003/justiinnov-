/**
 * Les guides vidéo (décision 118) : un parcours filmé par
 * `scripts/tourner-guides.mts` sur la pile de démonstration, en français et
 * en anglais, avec ses sous-titres.
 *
 * Chaque guide montre une capacité de la matrice (`accounts/permissions.py`)
 * et ne s'affiche qu'à qui l'a : un compte ne voit pas le tutoriel d'un
 * geste qui lui est fermé. Le titre et la description viennent du
 * dictionnaire (`guides.liste.<id>.titre`, `guides.liste.<id>.description`).
 *
 * Ce module ne dépend de rien : le script de tournage le lit aussi, pour
 * filmer exactement les guides que l'interface propose. Une capacité mal
 * orthographiée ne passe pas la vérification de types : `guidesVisibles`
 * reçoit le `can` de l'interface, typé par les clés de la matrice.
 */

/**
 * Un guide : `id` nomme ses fichiers (`/guides/<langue>/<id>.webm`, `.vtt`,
 * `.jpg`), `capacite` est la capacité qu'il enseigne — sans elle, il ne
 * s'affiche pas.
 */
export const GUIDES = [
  { id: "ouvrir-un-projet", capacite: "projets.create" },
  { id: "saisir-une-ligne", capacite: "expenses.create" },
  { id: "joindre-une-piece", capacite: "proofs.upload" },
  { id: "soumettre-un-dossier", capacite: "dossiers.submit" },
  { id: "importer-un-classeur", capacite: "data.import" },
] as const

export type IdDeGuide = (typeof GUIDES)[number]["id"]
export type CapaciteDeGuide = (typeof GUIDES)[number]["capacite"]

/** Les langues filmées : celles de l'interface. */
export const LANGUES_DES_GUIDES = ["fr", "en"] as const
export type LangueDeGuide = (typeof LANGUES_DES_GUIDES)[number]

/** La langue de l'interface, ramenée à une langue filmée (le français sinon). */
export function langueDeGuide(langue: string | undefined): LangueDeGuide {
  return langue?.startsWith("en") ? "en" : "fr"
}

/** Adresse d'un fichier du guide : la vidéo, ses sous-titres ou son affiche. */
export function fichierDuGuide(id: string, langue: LangueDeGuide, extension: "webm" | "vtt" | "jpg") {
  return `/guides/${langue}/${id}.${extension}`
}

/** Les guides qu'un compte peut suivre : ceux des capacités qu'il a. */
export function guidesVisibles(can: (capacite: CapaciteDeGuide) => boolean) {
  return GUIDES.filter((guide) => can(guide.capacite))
}
