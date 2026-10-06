/**
 * Ce que le tournage des guides (décision 118) établit avant d'ouvrir le
 * navigateur : la langue, les guides à tourner, l'encodeur, les libellés —
 * et, s'il échoue, ce qu'il dit. Tout ici est pur : aucune lecture de
 * `process.env`, aucun fichier, aucun processus. `tourner-guides.mts` lit
 * l'environnement et le passe ; ces fonctions se testent sans base ni
 * navigateur (`selection.test.mts`).
 *
 * Une erreur de réglage doit arrêter le tournage AVANT le premier geste :
 * après, la base jetable a déjà reçu un projet et un changement de profil,
 * et il faut la recréer.
 */
import { GUIDES, LANGUES_DES_GUIDES, type IdDeGuide, type LangueDeGuide } from "../../src/lib/guides.ts"

/** `GUIDES_LANGUE` : obligatoire, une seule langue par base neuve. */
export function langueDuTournage(valeur: string | undefined): LangueDeGuide {
  const langue = valeur?.trim()
  if (!langue || !(LANGUES_DES_GUIDES as readonly string[]).includes(langue)) {
    throw new Error(`GUIDES_LANGUE doit valoir ${LANGUES_DES_GUIDES.join(" ou ")}, une langue par base neuve.`)
  }
  return langue as LangueDeGuide
}

/**
 * `GUIDES_SEULS=saisir-une-ligne,…` restreint le tournage, le temps de
 * mettre un guide au point : chaque guide reprend ce que le précédent a
 * créé (le projet, la ligne, la pièce), un guide seul se tourne donc sur
 * une base où les précédents ont déjà été joués.
 *
 * Absente, la variable tourne tous les guides, dans l'ordre de
 * `src/lib/guides.ts`. Présente, elle doit nommer au moins un guide connu :
 * une valeur vide (`""`, `","`, `" "`) ou un nom inconnu arrête tout,
 * plutôt que de finir en succès sans rien avoir tourné — les anciennes
 * vidéos, peut-être périmées, resteraient en place sans que personne le
 * voie.
 */
export function guidesDuTournage(valeur: string | undefined): IdDeGuide[] {
  const tous = GUIDES.map((guide) => guide.id)
  if (valeur === undefined) return tous
  const demandes = valeur
    .split(",")
    .map((nom) => nom.trim())
    .filter(Boolean)
  if (!demandes.length) {
    throw new Error(`GUIDES_SEULS ne nomme aucun guide. Retirez la variable pour tout tourner, ou nommez-en parmi : ${tous.join(", ")}.`)
  }
  const inconnus = demandes.filter((id) => !(tous as string[]).includes(id))
  if (inconnus.length) throw new Error(`Guides inconnus : ${inconnus.join(", ")}. Connus : ${tous.join(", ")}.`)
  return tous.filter((id) => demandes.includes(id))
}

/**
 * La sortie de `ffmpeg -hide_banner -encoders` propose-t-elle l'encodeur
 * VP8 `libvpx`, celui du réencodage ? La ligne ressemble à
 * ` V....D libvpx   libvpx VP8 (codec vp8)` ; `libvpx-vp9` ne suffit pas.
 */
export function proposeLibvpx(sortie: string) {
  return /^\s*V[.A-Z]{5}\s+libvpx\s/m.test(sortie)
}

/**
 * Le message qui arrête le tournage quand l'encodeur ne convient pas. Il
 * nomme `GUIDES_FFMPEG` : c'est la variable à corriger, qu'elle soit
 * fausse ou qu'il faille la poser.
 */
export function ffmpegInutilisable(chemin: string, designeParGuidesFfmpeg: boolean, raison: string) {
  const origine = designeParGuidesFfmpeg
    ? `GUIDES_FFMPEG désigne ${chemin}`
    : `le ffmpeg des navigateurs de Playwright (${chemin})`
  return new Error(
    `${origine}, inutilisable pour réencoder les guides : ${raison}. ` +
      "Désignez par GUIDES_FFMPEG un ffmpeg qui encode en VP8 (libvpx).",
  )
}

/**
 * Un libellé du dictionnaire de l'interface (`src/i18n/<langue>.json`),
 * valeurs interpolées. Une clé absente, même par un segment intermédiaire
 * (`inexistant.cle`), se nomme : le script clique ce qu'une personne lit,
 * et un libellé renommé doit dire lequel.
 */
export function libelle(
  brut: Record<string, unknown>,
  langue: string,
  cle: string,
  valeurs: Record<string, string> = {},
) {
  let texte: unknown = brut
  for (const morceau of cle.split(".")) {
    texte = texte !== null && typeof texte === "object" ? (texte as Record<string, unknown>)[morceau] : undefined
  }
  if (typeof texte !== "string") throw new Error(`Clé absente du dictionnaire ${langue} : ${cle}`)
  return texte.replace(/\{\{(\w+)\}\}/g, (_, nom: string) => valeurs[nom] ?? "")
}

/**
 * L'erreur d'un geste qui a échoué, augmentée des erreurs de console déjà
 * collectées : un `waitFor` qui expire après une réponse 5xx ne dit que
 * « délai dépassé », la console dit pourquoi. La cause d'origine reste
 * attachée (`cause`) pour sa pile.
 */
export function echecDuGeste(quoi: string, cause: unknown, erreursDeConsole: readonly string[]) {
  const message = cause instanceof Error ? cause.message : String(cause)
  const suite =
    erreursDeConsole.length > 0
      ? `\nErreurs de console collectées avant l'échec :\n${erreursDeConsole.join("\n")}`
      : "\nAucune erreur de console avant l'échec."
  return new Error(`Échec pendant ${quoi} : ${message}${suite}`, { cause })
}
