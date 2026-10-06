/**
 * Le plateau des guides vidéo : une page filmée, un pointeur visible, des
 * légendes horodatées qui deviennent les sous-titres (WebVTT).
 *
 * Playwright filme la page mais pas la souris : sans repère, on verrait
 * des champs se remplir tout seuls. Un pointeur et un halo, injectés dans
 * la page, montrent où l'on clique ; ils ne font partie que de la vidéo.
 * Leurs couleurs sont les jetons de l'interface (`--foreground`,
 * `--background`, `--primary`) : ils suivent le thème filmé.
 *
 * Chaque légende capture aussi la page (`captures`) : le tournage compare
 * ces captures à la vidéo réencodée et échoue si l'enregistrement a perdu
 * des images (`controle-images.ts`).
 */
import type { Locator, Page } from "playwright"

/** Ce qu'une légende laisse le temps de lire : un plancher, puis au caractère. */
export function tempsDeLecture(texte: string) {
  return Math.max(2500, 1200 + texte.length * 55)
}

/**
 * Délai entre le début d'une légende et la capture de la page que le
 * contrôle des images compare à la vidéo : le temps qu'un rendu en cours
 * s'achève, sans approcher du geste suivant (une légende dure au moins
 * 2,5 s, `tempsDeLecture`).
 */
export const DELAI_DE_LA_CAPTURE = 300

/** Des millisecondes en horodatage WebVTT, `hh:mm:ss.mmm`. */
export function horodatage(ms: number) {
  const total = Math.max(0, Math.round(ms))
  const heures = Math.floor(total / 3_600_000)
  const minutes = Math.floor((total % 3_600_000) / 60_000)
  const secondes = Math.floor((total % 60_000) / 1000)
  const millis = total % 1000
  const deux = (n: number) => String(n).padStart(2, "0")
  return `${deux(heures)}:${deux(minutes)}:${deux(secondes)}.${String(millis).padStart(3, "0")}`
}

export interface Repere {
  /** Millisecondes depuis le début de la vidéo. */
  debut: number
  texte: string
}

/** Les sous-titres : chaque légende dure jusqu'à la suivante, la dernière jusqu'à la fin. */
export function sousTitres(reperes: Repere[], fin: number) {
  const blocs = reperes.map((repere, i) => {
    const suivant = reperes[i + 1]?.debut ?? fin
    return `${i + 1}\n${horodatage(repere.debut)} --> ${horodatage(suivant)}\n${repere.texte}\n`
  })
  return `WEBVTT\n\n${blocs.join("\n")}`
}

/**
 * Installé avant chaque chargement de page (`addInitScript`) : le pointeur
 * et le halo, et `window.__guide.viser()` pour les déplacer.
 *
 * C'est du JavaScript en texte, pas une fonction : `tsx` ajoute aux
 * fonctions qu'il transpile des appels (`__name`) qui n'existent pas dans
 * la page, et le script s'y arrêterait sans un mot.
 */
export const POINTEUR = `(() => {
  const installer = () => {
    if (document.getElementById("guide-pointeur") || !document.body) return
    const pointeur = document.createElement("div")
    pointeur.id = "guide-pointeur"
    pointeur.innerHTML =
      '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l16 9-7 2-3 7z" ' +
      'fill="var(--foreground)" stroke="var(--background)" stroke-width="1.5" stroke-linejoin="round"/></svg>'
    Object.assign(pointeur.style, {
      position: "fixed", left: "50%", top: "45%", zIndex: "2147483647", pointerEvents: "none",
      transition: "left 600ms ease-in-out, top 600ms ease-in-out",
    })
    const halo = document.createElement("div")
    halo.id = "guide-halo"
    Object.assign(halo.style, {
      position: "fixed", zIndex: "2147483646", pointerEvents: "none", borderRadius: "10px",
      outline: "3px solid var(--primary)",
      boxShadow: "0 0 0 6px color-mix(in oklch, var(--primary) 20%, transparent)",
      opacity: "0", transition: "all 300ms ease-in-out",
    })
    document.body.append(halo, pointeur)
  }
  window.__guide = {
    viser(x, y, largeur, hauteur) {
      installer()
      const pointeur = document.getElementById("guide-pointeur")
      const halo = document.getElementById("guide-halo")
      pointeur.style.left = (x + largeur / 2) + "px"
      pointeur.style.top = (y + hauteur / 2) + "px"
      Object.assign(halo.style, {
        left: (x - 6) + "px", top: (y - 6) + "px",
        width: (largeur + 12) + "px", height: (hauteur + 12) + "px", opacity: "1",
      })
    },
    effacer() {
      const halo = document.getElementById("guide-halo")
      if (halo) halo.style.opacity = "0"
    },
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", installer)
  else installer()
})()`

/** Une prise : la page filmée, ses légendes et leurs horodatages. */
export class Scene {
  readonly reperes: Repere[] = []
  /** Une capture PNG de la page par légende, dans l'ordre des repères. */
  readonly captures: Buffer[] = []
  readonly page: Page
  private readonly legendes: readonly string[]
  private readonly t0 = Date.now()

  constructor(page: Page, legendes: readonly string[]) {
    this.page = page
    this.legendes = legendes
  }

  /** Écoulé depuis le début de la vidéo, en millisecondes. */
  maintenant() {
    return Date.now() - this.t0
  }

  /**
   * Affiche la légende `i` (un sous-titre) et laisse le temps de la lire.
   * Pendant ce temps, la page est capturée telle qu'elle est : c'est ce que
   * la vidéo doit montrer sous ce sous-titre. Le curseur de saisie reste
   * visible (`caret: "initial"`), comme dans la vidéo. La capture ne
   * rallonge pas la légende : on n'attend que ce qui reste de son temps de
   * lecture.
   */
  async dire(i: number) {
    const texte = this.legendes[i]
    if (texte === undefined) throw new Error(`Légende ${i} absente.`)
    const debut = this.maintenant()
    this.reperes.push({ debut, texte })
    await this.page.waitForTimeout(DELAI_DE_LA_CAPTURE)
    this.captures.push(await this.page.screenshot({ type: "png", caret: "initial" }))
    await this.page.waitForTimeout(Math.max(0, tempsDeLecture(texte) - (this.maintenant() - debut)))
  }

  /** Amène le pointeur sur la cible et l'entoure. */
  async montrer(cible: Locator) {
    await cible.scrollIntoViewIfNeeded()
    const boite = await cible.boundingBox()
    if (!boite) throw new Error(`Cible invisible : ${cible}`)
    await this.page.evaluate(
      ({ x, y, width, height }) =>
        (window as unknown as { __guide: { viser: (...n: number[]) => void } }).__guide.viser(x, y, width, height),
      boite,
    )
    await this.page.waitForTimeout(900)
  }

  /** Retire le halo : l'écran se lit sans repère. */
  async relacher() {
    await this.page.evaluate(() => (window as unknown as { __guide: { effacer: () => void } }).__guide.effacer())
  }

  /**
   * Un clic peut changer de page ou fermer un dialogue : le halo, posé sur
   * la page, resterait à sa place au-dessus d'un autre contenu. Il s'efface
   * donc dès le clic ; le pointeur, lui, reste où il a cliqué.
   */
  async cliquer(cible: Locator) {
    await this.montrer(cible)
    await cible.click()
    await this.relacher()
    await this.page.waitForTimeout(500)
  }

  /** Saisit au rythme d'une personne : la vidéo montre le texte s'écrire. */
  async saisir(cible: Locator, texte: string) {
    await this.montrer(cible)
    await cible.click()
    await cible.pressSequentially(texte, { delay: 45 })
    await this.page.waitForTimeout(300)
  }

  /** Remplit d'un coup un champ qui ne se tape pas (date, heure). */
  async remplir(cible: Locator, valeur: string) {
    await this.montrer(cible)
    await cible.fill(valeur)
    await this.page.waitForTimeout(300)
  }

  async choisir(cible: Locator, option: { label: string } | { index: number }) {
    await this.montrer(cible)
    await cible.selectOption(option)
    await this.page.waitForTimeout(500)
  }

  /** Une pause sur l'écran courant, pour que la vidéo laisse voir le résultat. */
  async attendre(ms: number) {
    await this.page.waitForTimeout(ms)
  }
}
