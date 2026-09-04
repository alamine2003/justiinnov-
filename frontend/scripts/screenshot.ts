/**
 * Revue visuelle : parcourt l'application et capture les écrans principaux.
 *
 * Les identifiants ne sont jamais codés en dur — ils viennent de
 * l'environnement :
 *
 *   SHOT_HQ_USER=admin.innov SHOT_HQ_PASSWORD=… \
 *   SHOT_COUNTRY_USER=togo.innov SHOT_COUNTRY_PASSWORD=… \
 *   npx tsx scripts/screenshot.ts
 *
 * Le script échoue (code de sortie 1) sur toute erreur de console et sur
 * toute attente non tenue : un compte qui verrait des lignes hors de son
 * périmètre, une redirection absente, un titre qui manque.
 */
import { chromium, type Browser, type Page } from "playwright"

const BASE = process.env.SHOT_BASE ?? "http://localhost:5173"
const OUT = process.env.SHOT_OUT ?? "/tmp"

function credentials(prefix: string) {
  const user = process.env[`SHOT_${prefix}_USER`]
  const password = process.env[`SHOT_${prefix}_PASSWORD`]
  if (!user || !password) {
    throw new Error(
      `SHOT_${prefix}_USER et SHOT_${prefix}_PASSWORD doivent être définis.`,
    )
  }
  return { user, password }
}

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

async function newPage(browser: Browser, viewport = { width: 1440, height: 900 }) {
  const page = await browser.newPage({ viewport })
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`[console] ${m.text()}`)
  })
  page.on("pageerror", (e) => errors.push(`[pageerror] ${String(e)}`))
  return page
}

async function login(page: Page, prefix: string) {
  const { user, password } = credentials(prefix)
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" })
  await page.fill("#username", user)
  await page.fill("#password", password)
  await page.click("button[type=submit]")
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 15000,
  })
  await page.waitForTimeout(1500)
  return user
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
  const hqNav = await hq.locator("nav[aria-label='Navigation principale'] a").allTextContents()
  expect(hqNav.some((t) => t.includes("Configuration")), "le siège voit « Configuration »")
  expect(hqNav.some((t) => t.includes("Audit")), "le siège voit « Audit »")
  expect((await hq.textContent("h1"))?.includes("Pilotage") ?? false, "le tableau de bord s'ouvre")
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

  await hq.locator('button[aria-label^="Notifications"]').click()
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
  expect(hqDossiers > 0, `des dossiers sont listés (${hqDossiers})`)
  await shot(hq, "dossiers")

  // Premier dossier : lignes de dépenses, justificatifs, workflow, aperçu.
  const firstDossier = hq.locator("tbody tr a").first()
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
    const apercu = hq.locator('button[aria-label^="Prévisualiser"]').first()
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
  expect((await hq.locator("tbody tr").count()) > 0, "le registre a des lignes")
  await shot(hq, "registre")

  await goto(hq, "/audit", 1200)
  expect((await hq.locator("tbody tr").count()) > 0, "le journal d'audit a des entrées")
  await shot(hq, "audit")

  await goto(hq, "/countries")
  const hqCountries = await hq.locator("tbody tr").count()
  expect(hqCountries > 1, `le siège voit plusieurs pays (${hqCountries})`)
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
    expect((await hq.locator("tbody tr").count()) > 0, `Configuration › ${onglet} a des lignes`)
    await shot(hq, nom)
  }

  // --- Parcours pays : périmètre restreint --------------------------------
  const rep = await newPage(browser)
  const repUser = await login(rep, "COUNTRY")
  console.log(`\n=== REPRÉSENTANT PAYS (${repUser}) ===`)
  const perimetre = (await rep.textContent("header p.text-xs")) ?? ""
  expect(!perimetre.includes("Siège"), `le périmètre affiché est celui d'un pays (${perimetre})`)
  const repNav = await rep.locator("nav[aria-label='Navigation principale'] a").allTextContents()
  expect(!repNav.some((t) => t.includes("Configuration")), "le pays ne voit pas « Configuration »")
  expect(!repNav.some((t) => t.includes("Audit")), "le pays ne voit pas « Audit »")
  await goto(rep, "/dossiers")
  const repDossiers = await rep.locator("tbody tr").count()
  expect(repDossiers <= hqDossiers, `le pays voit au plus autant de dossiers que le siège (${repDossiers})`)
  await shot(rep, "dossiers_representant")

  await goto(rep, "/countries")
  expect((await rep.locator("tbody tr").count()) <= 1, "le pays ne voit que son pays")
  expect((await rep.locator('button:has-text("Ajouter")').count()) === 0, "le pays n'a pas de bouton « Ajouter »")
  await shot(rep, "countries_representant")

  await goto(rep, "/budgets", 1200)
  expect(
    (await rep.locator('button:has-text("Attribuer")').count()) === 0,
    "le pays n'a pas de bouton « Attribuer une enveloppe »",
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
