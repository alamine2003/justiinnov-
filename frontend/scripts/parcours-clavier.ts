/**
 * Parcours au clavier seul (décision 130) : ce qu'axe ne voit pas.
 *
 *   SHOT_COUNTRY_USER=… SHOT_COUNTRY_PASSWORD=… SHOT_COUNTRY_TOTP_SECRET=… \
 *   npx tsx scripts/parcours-clavier.ts
 *
 * axe juge un écran figé ; il ne sait pas si la touche Tab mène quelque part.
 * Ce script refait au clavier, avec le compte pays, le chemin de la
 * déclaration et échoue (code de sortie 1) si :
 *
 * - la connexion ne suit pas l'ordre identifiant, mot de passe, bouton ;
 * - un élément atteint par Tab n'a pas d'indicateur de focus visible ;
 * - « Projets » ne s'atteint pas depuis la navigation, ni « Nouveau
 *   projet » depuis la page ;
 * - le dialogue ouvert au clavier laisse le focus sortir (Tab et
 *   Maj+Tab), ou ne le rend pas au bouton qui l'a ouvert après Échap.
 *
 * Rien n'est enregistré : le dialogue se ferme sans être soumis.
 */
import { chromium, type Page } from "playwright"
import { credentials, estLeRefusAttenduDuCode, signIn } from "./login.ts"

const BASE = process.env.SHOT_BASE ?? "http://localhost:5173"
/** Au-delà, une cible qu'on n'atteint pas est une impasse, pas un long trajet. */
const TABULATIONS_MAX = 60
/**
 * Une frappe à vitesse humaine : la garde de focus d'un dialogue base-ui
 * renvoie le focus au début du dialogue au tour suivant de la boucle
 * d'affichage ; tabuler plus vite la ferait croire percée.
 */
const ENTRE_DEUX_TOUCHES_MS = 120

const echecs: string[] = []

function attendre(condition: boolean, message: string) {
  console.log(`  ${condition ? "✓" : "✗"} ${message}`)
  if (!condition) echecs.push(message)
}

/** L'élément qui a le focus : son nom lisible, et s'il montre qu'il l'a. */
async function focusActuel(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null
    if (!el || el === document.body) return { nom: "(page)", visible: false, id: "", dansDialogue: false }
    const style = getComputedStyle(el)
    const contour = style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0
    const anneau = style.boxShadow !== "none" && style.boxShadow !== ""
    const nom = (el.getAttribute("aria-label") || el.textContent || el.id || el.tagName).trim().replace(/\s+/g, " ")
    return {
      nom: `${el.tagName.toLowerCase()} « ${nom.slice(0, 60)} »`,
      visible: contour || anneau,
      id: el.id,
      dansDialogue: Boolean(el.closest("[role=dialog]")),
    }
  })
}

/**
 * Tabule jusqu'à l'élément que `cible` reconnaît, en vérifiant au passage
 * que chaque élément traversé montre son focus.
 */
async function tabulerJusqua(page: Page, cible: (nom: string) => boolean, libelle: string) {
  const sansIndicateur = new Set<string>()
  for (let i = 0; i < TABULATIONS_MAX; i++) {
    await page.keyboard.press("Tab")
    await page.waitForTimeout(ENTRE_DEUX_TOUCHES_MS)
    const focus = await focusActuel(page)
    // « (page) » : le focus passe un instant au navigateur, hors du document.
    if (!focus.visible && focus.nom !== "(page)") sansIndicateur.add(focus.nom)
    if (cible(focus.nom)) {
      attendre(sansIndicateur.size === 0, `focus visible sur chaque élément jusqu'à ${libelle}${sansIndicateur.size ? ` — sans indicateur : ${[...sansIndicateur].join(", ")}` : ""}`)
      attendre(true, `${libelle} atteint en ${i + 1} tabulation(s)`)
      return true
    }
  }
  attendre(false, `${libelle} atteint au clavier (pas trouvé en ${TABULATIONS_MAX} tabulations)`)
  return false
}

async function main() {
  const compte = credentials("COUNTRY")
  const navigateur = await chromium.launch()
  const contexte = await navigateur.newContext({ viewport: { width: 1440, height: 900 }, locale: "fr-FR" })
  const page = await contexte.newPage()
  page.on("console", (m) => {
    if (m.type() === "error" && !estLeRefusAttenduDuCode(m)) echecs.push(`[console] ${m.text()}`)
  })
  page.on("pageerror", (e) => echecs.push(`[pageerror] ${String(e)}`))

  console.log("Connexion")
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" })
  // Thème et langue précèdent le formulaire ; on ne retient que ses trois
  // éléments, dans l'ordre où Tab les atteint.
  const ordre: string[] = []
  for (let i = 0; i < 12 && ordre.length < 3; i++) {
    await page.keyboard.press("Tab")
    const etape = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (el?.id === "username" || el?.id === "password") return el.id
      return el instanceof HTMLButtonElement && el.type === "submit" ? "bouton" : null
    })
    if (etape && !ordre.includes(etape)) ordre.push(etape)
  }
  attendre(ordre.join(",") === "username,password,bouton", `identifiant, mot de passe puis bouton (${ordre.join(", ")})`)

  // La connexion elle-même suit le chemin commun (double authentification
  // comprise) ; ce qui suit se fait au clavier seul.
  await signIn(page, BASE, compte)
  await page.waitForLoadState("networkidle")

  console.log("Navigation")
  await page.locator("body").focus()
  if (await tabulerJusqua(page, (nom) => nom.startsWith("a « Projets"), "le lien « Projets »")) {
    await page.keyboard.press("Enter")
    await page.waitForURL((url) => url.pathname.startsWith("/projets"))
    await page.waitForLoadState("networkidle")
    attendre(true, "Entrée ouvre la page des projets")
  }

  console.log("Dialogue")
  if (await tabulerJusqua(page, (nom) => nom.includes("Nouveau projet"), "le bouton « Nouveau projet »")) {
    await page.keyboard.press("Enter")
    await page.getByRole("dialog").waitFor()
    await page.waitForTimeout(300)
    attendre((await focusActuel(page)).dansDialogue, "le focus entre dans le dialogue à l'ouverture")
    let sorti = false
    for (const touche of ["Tab", "Shift+Tab"]) {
      for (let i = 0; i < 25; i++) {
        await page.keyboard.press(touche)
        await page.waitForTimeout(ENTRE_DEUX_TOUCHES_MS)
        if (!(await focusActuel(page)).dansDialogue) sorti = true
      }
    }
    attendre(!sorti, "le focus reste dans le dialogue (Tab et Maj+Tab)")
    await page.keyboard.press("Escape")
    await page.getByRole("dialog").waitFor({ state: "hidden" })
    const retour = await focusActuel(page)
    attendre(retour.nom.includes("Nouveau projet"), `Échap rend le focus au bouton qui a ouvert le dialogue (${retour.nom})`)
  }

  await navigateur.close()
  console.log("Échecs :", echecs.length ? echecs : "aucun")
  if (echecs.length) process.exitCode = 1
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
