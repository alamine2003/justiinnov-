/**
 * Le garde-fou de cible du tournage des guides (décision 118). Le tournage écrit pour de bon dans la base qu'il vise : il change
 * la langue du profil, ouvre un projet, saisit une ligne, dépose une pièce,
 * soumet un dossier (irréversible) et importe un classeur. Rien de cela ne
 * se supprime, et la remise à zéro des essais ne se rejoue pas (décision
 * 113). Les jeux de démonstration exigent `--base-jetable` pour la même
 * raison ; ici, la cible doit être la machine locale, sauf levée explicite.
 *
 * Le mot de passe n'est pas une barrière : un manager réel non enrôlé se
 * connecte sans code tant que `DJANGO_TOTP_REQUIRED` est faux.
 *
 * Pur, comme `selection.ts` : aucune lecture de `process.env`.
 * `tourner-guides.mts` passe l'adresse et la levée, et appelle ce
 * garde-fou avant d'ouvrir le navigateur, donc avant tout geste.
 */

/** Les hôtes de la machine locale, tels que `URL.hostname` les écrit. */
export const HOTES_LOCAUX = ["localhost", "127.0.0.1", "[::1]"] as const

/** La seule valeur de `GUIDES_CIBLE_JETABLE` qui lève le garde-fou. */
export const LEVEE = "oui"

/**
 * Vérifie que `base` (`SHOT_BASE`) vise une base jetable et la rend.
 * L'hôte doit être local (`HOTES_LOCAUX`) ; un autre hôte n'est accepté que
 * si `levee` (`GUIDES_CIBLE_JETABLE`) vaut exactement `oui` — une valeur
 * approchante (`1`, `true`, `non`) refuse plutôt que de deviner. Une adresse
 * qui ne se lit pas, ou qui n'est pas en `http`/`https`, refuse toujours.
 */
export function exigerUneCibleJetable(base: string, levee: string | undefined): string {
  let url: URL
  try {
    url = new URL(base)
  } catch {
    throw new Error(`SHOT_BASE n'est pas une adresse lisible (${JSON.stringify(base)}) : attendu par exemple http://localhost:5173.`)
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`SHOT_BASE doit être une adresse http ou https, pas ${url.protocol} (${base}).`)
  }
  if ((HOTES_LOCAUX as readonly string[]).includes(url.hostname)) return base
  const valeur = levee?.trim()
  if (valeur === LEVEE) return base
  const precision =
    valeur === undefined || valeur === ""
      ? ""
      : ` GUIDES_CIBLE_JETABLE vaut ${JSON.stringify(levee)} : seule la valeur « ${LEVEE} » lève le garde-fou.`
  throw new Error(
    "Le tournage des guides écrit dans la base visée un projet, une ligne, une pièce, " +
      "un dossier soumis et un import, qui ne se suppriment pas : réservé à une base jetable. " +
      `SHOT_BASE vise ${url.hostname}, qui n'est ni ${HOTES_LOCAUX.join(", ni ")}.` +
      precision +
      ` Relancez avec GUIDES_CIBLE_JETABLE=${LEVEE} si c'est bien une base jetable.`,
  )
}
