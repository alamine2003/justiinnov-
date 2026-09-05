/**
 * Revue visuelle : parcourt l'application et capture les écrans principaux.
 *
 * Les identifiants ne sont jamais codés en dur — ils viennent de
 * l'environnement :
 *
 *   SHOT_HQ_USER=admin.innov SHOT_HQ_PASSWORD=… SHOT_HQ_TOTP_SECRET=… \
 *   SHOT_COUNTRY_USER=togo.innov SHOT_COUNTRY_PASSWORD=… SHOT_COUNTRY_TOTP_SECRET=… \
 *   npx tsx scripts/screenshot.ts
 *
 * Le script échoue (code de sortie 1) sur toute erreur de console et sur
 * toute attente non tenue : un compte qui verrait des lignes hors de son
 * périmètre, une redirection absente, un titre qui manque.
 */
import { chromium, type Browser, type Page } from "playwright"
import { credentials, signIn } from "./login.ts"

const BASE = process.env.SHOT_BASE ?? "http://localhost:5173"
const OUT = process.env.SHOT_OUT ?? "/tmp"
/**
 * `SHOT_EXPECT_DATA=0` : la pile est vide (pas de dossier, pas d'entrée de
 * journal) ; les attentes sur la présence de données sont alors consignées
 * sans faire échouer le script. Les attentes sur les droits et la navigation
 * restent exigées.
 */
const EXPECT_DATA = process.env.SHOT_EXPECT_DATA !== "0"

const errors: string[] = []
const failures: string[] = []

/** Attente vérifiée : consignée, elle fait échouer le script sans l'arrêter. */
function expect(condition: boolean, message: string) {
  if (condition) {
    console.log(`  ✓ ${message}`)
  } else {
    console.log(`  ✗ ${message}`)
    failures.push(message)
  }
}

/** Attente sur la présence de données : facultative quand la pile est vide. */
function expectData(condition: boolean, message: string) {
  if (!EXPECT_DATA && !condition) {
    console.log(`  – ${message} (pile sans données, SHOT_EXPECT_DATA=0)`)
    return
  }
  expect(condition, message)
}

async function newPage(browser: Browser, viewport = { width: 1440, height: 900 }) {
  // Le navigateur de Playwright se présente en anglais ; l'interface suivrait
  // cette langue et les attentes ci-dessous, écrites en français, échoueraient.
  const page = await browser.newPage({ viewport, locale: "fr-FR" })
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`[console] ${m.text()}`)
  })
  page.on("pageerror", (e) => errors.push(`[pageerror] ${String(e)}`))
  return page
}

async function login(page: Page, prefix: string) {
  const account = credentials(prefix)
  await signIn(page, BASE, account)
  await page.waitForTimeout(1500)
  // Les attentes ci-dessous sont écrites en français ; la préférence du
  // profil l'emporte sur celle du navigateur, elle est donc fixée d'abord.
  await setLanguage(page, "fr")
  return account.user
}

/** Enregistre la langue sur le profil (`PATCH /api/me/`), avec le jeton de la session ouverte. */
async function setLanguage(page: Page, language: "fr" | "en") {
  const token = await page.evaluate(() => localStorage.getItem("justi_token"))
  if (!token) return
  const response = await page.request.patch(`${BASE}/api/me/`, {
    headers: { Authorization: `Token ${token}` },
    data: { language },
  })
  if (!response.ok()) {
    console.log(`  – la langue n'a pas pu être fixée (${response.status()})`)
    return
  }
  await page.reload({ waitUntil: "networkidle" })
  await page.waitForTimeout(800)
}

/** Le déploiement annonce-t-il la supervision (`GET /api/me/` → `supervision`) ? */
async function supervisionAnnoncee(page: Page): Promise<boolean> {
  const token = await page.evaluate(() => localStorage.getItem("justi_token"))
  if (!token) return false
  const response = await page.request.get(`${BASE}/api/me/`, {
    headers: { Authorization: `Token ${token}` },
  })
  if (!response.ok()) return false
  const me = (await response.json()) as { supervision?: boolean }
  return me.supervision === true
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `${OUT}/shot_${name}.png`, fullPage: false })
}

async function goto(page: Page, path: string, settle = 1000) {
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" })
  await page.waitForTimeout(settle)
}

async function main() {
  const browser = await chromium.launch()

  // --- Parcours siège : accès à tous les pays et à toutes les pages --------
  const hq = await newPage(browser)
  const hqUser = await login(hq, "HQ")
  console.log(`\n=== SIÈGE (${hqUser}) ===`)
  const hqNav = await hq.getByRole("navigation", { name: "Navigation principale" }).getByRole("link").allTextContents()
  expect(hqNav.some((t) => t.includes("Configuration")), "le siège voit « Configuration »")
  expect(hqNav.some((t) => t.includes("Audit")), "le siège voit « Audit »")
  expect((await hq.textContent("h1"))?.includes("Pilotage") ?? false, "le tableau de bord s'ouvre")
  // Le menu du compte : la supervision (Grafana) aux administrateurs, dans
  // un nouvel onglet ; la pastille 2FA pour un compte enrôlé (ceux de la CI
  // le sont).
  await hq.getByRole("button", { name: "Menu du compte" }).click()
  // Le menu s'ouvre avec une transition : compter ses entrées ou le
  // photographier avant la fin donnerait un menu vide ou translucide.
  await hq.getByRole("menu").waitFor({ state: "visible" })
  await hq.waitForTimeout(400)
  // « Supervision » n'est pas un droit mais un réglage de déploiement
  // (me.supervision) : la pile de la CI n'embarque pas Grafana.
  const supervisionActive = await supervisionAnnoncee(hq)
  const supervision = hq.getByRole("menuitem", { name: "Supervision" })
  expect(
    (await supervision.count()) === (supervisionActive ? 1 : 0),
    supervisionActive
      ? "le siège voit « Supervision » dans le menu du compte"
      : "sans Grafana déployé, « Supervision » n'apparaît pas",
  )
  if (supervisionActive) {
    expect(
      (await supervision.getAttribute("href")) === "/grafana/" &&
        (await supervision.getAttribute("target")) === "_blank" &&
        (await supervision.getAttribute("rel")) === "noopener noreferrer",
      "« Supervision » ouvre /grafana/ dans un nouvel onglet",
    )
  }
  expect(
    ((await hq.getByRole("menu").textContent()) ?? "").includes("2FA active"),
    "le menu du compte montre la pastille « 2FA active » d'un compte enrôlé",
  )
  await shot(hq, "menu_compte")
  await hq.keyboard.press("Escape")
  // Sans pays choisi, la consolidation ne propose pas de répartition : deux
  // équipes homonymes de pays différents fusionneraient. Le siège doit
  // d'abord choisir un pays.
  expect(
    ((await hq.textContent("main")) ?? "").includes("Choisissez un pays"),
    "la consolidation invite à choisir un pays pour la répartition",
  )
  await shot(hq, "pilotage")
  await hq.getByLabel("Pays").selectOption({ index: 1 })
  await hq.waitForTimeout(1200)
  expect((await hq.getByRole("tab").count()) >= 6, "la répartition d'un pays propose ses onglets")
  await shot(hq, "pilotage_pays")

  // Le sélecteur de langue est un groupe radio, comme celui du thème.
  await hq.getByRole("button", { name: "Langue de l'interface" }).click()
  const menuLangue = hq.getByRole("menu")
  await menuLangue.waitFor({ state: "visible" })
  await hq.waitForTimeout(300)
  expect(
    (await hq.getByRole("menuitemradio", { name: "English" }).count()) === 1,
    "le sélecteur de langue propose l'anglais",
  )
  await hq.getByRole("menuitemradio", { name: "English" }).click()
  await menuLangue.waitFor({ state: "hidden" })
  await hq.waitForTimeout(1200)
  const navAnglaise = await hq.getByRole("navigation", { name: "Main navigation" }).getByRole("link").allTextContents()
  expect(navAnglaise.some((t) => t.includes("Settings")), "l'interface passe en anglais")
  expect((await hq.getAttribute("html", "lang")) === "en", "<html lang> suit la langue")
  await shot(hq, "pilotage_en")
  await hq.getByRole("button", { name: "Interface language" }).click()
  await menuLangue.waitFor({ state: "visible" })
  await hq.waitForTimeout(300)
  await hq.getByRole("menuitemradio", { name: "Français" }).click()
  await menuLangue.waitFor({ state: "hidden" })
  await hq.waitForTimeout(1200)
  expect((await hq.getAttribute("html", "lang")) === "fr", "le retour au français est appliqué")

  await hq.getByRole("button", { name: /^Notifications/ }).click()
  await hq.waitForTimeout(900)
  expect(
    ((await hq.textContent("[data-slot=sheet-title]")) ?? "").includes("Notifications"),
    "le panneau de notifications s'ouvre",
  )
  await shot(hq, "notifications")
  await hq.keyboard.press("Escape")
  await hq.waitForTimeout(400)

  await goto(hq, "/dossiers")
  const hqDossiers = await hq.locator("tbody tr").count()
  expectData(hqDossiers > 0, `des dossiers sont listés (${hqDossiers})`)
  await shot(hq, "dossiers")

  // Premier dossier : lignes de dépenses, justificatifs, workflow, aperçu.
  const firstDossier = hq.locator("tbody tr").getByRole("link").first()
  if (await firstDossier.count()) {
    await firstDossier.click()
    await hq.waitForURL("**/dossiers/*", { timeout: 15000 })
    await hq.waitForTimeout(1200)
    expect(Boolean(await hq.textContent("h1")), "la fiche du dossier porte son N°ORDRE")
    await shot(hq, "dossier_detail")

    // Un dialogue : la justification ou, à défaut, le dépôt de pièce.
    const dialogueBouton = hq.getByRole("button", { name: /Marquer justifié|Déposer|Ajouter/ }).first()
    if (await dialogueBouton.count()) {
      await dialogueBouton.click()
      await hq.waitForTimeout(600)
      expect((await hq.getByRole("dialog").count()) > 0, "un dialogue s'ouvre sur la fiche")
      await shot(hq, "dossier_dialogue")
      await hq.keyboard.press("Escape")
      await hq.waitForTimeout(400)
    }

    // L'aperçu d'une pièce, s'il en existe une prévisualisable.
    const apercu = hq.getByRole("button", { name: /^Prévisualiser/ }).first()
    if (await apercu.count()) {
      await apercu.click()
      await hq.waitForTimeout(1500)
      expect((await hq.getByRole("dialog").count()) > 0, "l'aperçu d'une pièce s'ouvre")
      await shot(hq, "dossier_apercu")
      await hq.keyboard.press("Escape")
      await hq.waitForTimeout(400)
    } else {
      console.log("  – aucune pièce prévisualisable sur ce dossier")
    }
  }

  await goto(hq, "/registre", 1200)
  expectData((await hq.locator("tbody tr").count()) > 0, "le registre a des lignes")
  expect(
    (await hq.getByRole("button", { name: "Exporter" }).count()) === 1,
    "le registre propose le menu « Exporter » au siège",
  )
  await shot(hq, "registre")

  await goto(hq, "/audit", 1200)
  expectData((await hq.locator("tbody tr").count()) > 0, "le journal d'audit a des entrées")
  await shot(hq, "audit")

  await goto(hq, "/countries")
  const hqCountries = await hq.locator("tbody tr").count()
  expectData(hqCountries > 1, `le siège voit plusieurs pays (${hqCountries})`)
  await shot(hq, "countries_hq")

  await goto(hq, "/budgets", 1200)
  expect((await hq.textContent("h1"))?.includes("Budgets") ?? false, "la page Budgets s'ouvre")
  await shot(hq, "budgets_pays")

  await hq.getByRole("tab", { name: "Enveloppes" }).click()
  await hq.waitForTimeout(600)
  await shot(hq, "budgets_enveloppes")

  await hq.getByRole("tab", { name: "Réallocations" }).click()
  await hq.waitForTimeout(600)
  await shot(hq, "budgets_reallocations")

  await goto(hq, "/configuration", 1200)
  const onglets = await hq.getByRole("tab").allTextContents()
  expect(onglets.includes("Permissions"), "la configuration propose l'onglet Permissions")
  await shot(hq, "configuration_general")

  for (const [onglet, nom] of [
    ["Utilisateurs", "configuration_utilisateurs"],
    ["Pays", "configuration_pays"],
    ["Permissions", "configuration_permissions"],
  ] as const) {
    await hq.getByRole("tab", { name: onglet }).click()
    await hq.waitForTimeout(900)
    expectData((await hq.locator("tbody tr").count()) > 0, `Configuration › ${onglet} a des lignes`)
    await shot(hq, nom)
  }

  // --- Parcours pays : périmètre restreint --------------------------------
  const rep = await newPage(browser)
  const repUser = await login(rep, "COUNTRY")
  console.log(`\n=== MANAGER DE PAYS (${repUser}) ===`)
  const perimetre = (await rep.getByRole("banner").textContent()) ?? ""
  expect(!perimetre.includes("Siège"), "le périmètre affiché est celui d'un pays, pas le siège")
  const repNav = await rep.getByRole("navigation", { name: "Navigation principale" }).getByRole("link").allTextContents()
  expect(!repNav.some((t) => t.includes("Configuration")), "le pays ne voit pas « Configuration »")
  expect(!repNav.some((t) => t.includes("Audit")), "le pays ne voit pas « Audit »")
  await rep.getByRole("button", { name: "Menu du compte" }).click()
  await rep.getByRole("menu").waitFor({ state: "visible" })
  await rep.waitForTimeout(400)
  expect(
    (await rep.getByRole("menuitem", { name: "Déconnexion" }).count()) === 1 &&
      (await rep.getByRole("menuitem", { name: "Supervision" }).count()) === 0,
    "le pays ne voit pas « Supervision »",
  )
  await rep.keyboard.press("Escape")
  await goto(rep, "/dossiers")
  const repDossiers = await rep.locator("tbody tr").count()
  expect(repDossiers <= hqDossiers, `le pays voit au plus autant de dossiers que le siège (${repDossiers})`)
  await shot(rep, "dossiers_representant")

  await goto(rep, "/countries")
  expect((await rep.locator("tbody tr").count()) <= 1, "le pays ne voit que son pays")
  expect((await rep.getByRole("button", { name: /Ajouter/ }).count()) === 0, "le pays n'a pas de bouton « Ajouter »")
  await shot(rep, "countries_representant")

  await goto(rep, "/budgets", 1200)
  expect(
    (await rep.getByRole("button", { name: /Attribuer/ }).count()) === 0,
    "le pays n'a pas de bouton « Attribuer une enveloppe »",
  )
  await goto(rep, "/registre", 1200)
  expect(
    (await rep.getByRole("button", { name: "Exporter" }).count()) === 0,
    "le pays n'a pas de menu « Exporter » sur le registre",
  )
  await shot(rep, "budgets_representant")

  // Pages réservées au siège : la garde ramène au tableau de bord.
  for (const chemin of ["/configuration", "/audit"]) {
    await rep.goto(`${BASE}${chemin}`)
    await rep.waitForURL((url) => url.pathname === "/", { timeout: 10000 }).catch(() => {})
    await rep.waitForTimeout(800)
    expect(new URL(rep.url()).pathname === "/", `${chemin} redirige le pays vers le tableau de bord`)
  }
  expect(
    ((await rep.textContent("main")) ?? "").includes("réservée au siège"),
    "la redirection est expliquée",
  )
  await shot(rep, "garde_siege")

  // --- Mobile : une page interne ne doit pas défiler horizontalement -------
  const mobile = await newPage(browser, { width: 390, height: 844 })
  await login(mobile, "COUNTRY")
  await goto(mobile, "/dossiers")
  const deborde = await mobile.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  )
  expect(!deborde, "la page ne défile pas horizontalement à 390 px")
  await mobile.getByRole("button", { name: "Ouvrir le menu" }).click()
  await mobile.waitForTimeout(500)
  expect((await mobile.getByRole("dialog").count()) > 0, "le menu replié s'ouvre")
  await shot(mobile, "dossiers_mobile")

  console.log("\nErreurs console :", errors.length ? errors : "aucune")
  console.log("Attentes non tenues :", failures.length ? failures : "aucune")
  await browser.close()
  if (errors.length || failures.length) process.exitCode = 1
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
