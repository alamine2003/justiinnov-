/**
 * Revue visuelle : parcourt l'application et capture les écrans principaux.
 *
 * Les identifiants ne sont jamais codés en dur — ils viennent de
 * l'environnement :
 *
 *   SHOT_HQ_USER=admin.innov SHOT_HQ_PASSWORD=… \
 *   SHOT_COUNTRY_USER=togo.innov SHOT_COUNTRY_PASSWORD=… \
 *   npx tsx scripts/screenshot.ts
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

async function newPage(browser: Browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
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

async function main() {
  const browser = await chromium.launch()

  // --- Parcours siège : accès à tous les pays et à toutes les pages --------
  const hq = await newPage(browser)
  const hqUser = await login(hq, "HQ")
  console.log(`\n=== SIÈGE (${hqUser}) ===`)
  console.log("Navigation :", await hq.locator("header a").allTextContents())
  console.log("Pilotage - titre :", await hq.textContent("h1"))
  console.log("Pilotage - onglets :", await hq.getByRole("tab").allTextContents())
  await shot(hq, "pilotage")

  await hq.locator('button[aria-label^="Notifications"]').click()
  await hq.waitForTimeout(900)
  console.log(
    "Notifications ouvertes :",
    (await hq.textContent("h2, [data-slot=sheet-title]")) ?? "—",
  )
  await shot(hq, "notifications")
  await hq.keyboard.press("Escape")
  await hq.waitForTimeout(400)

  await hq.goto(`${BASE}/dossiers`, { waitUntil: "networkidle" })
  await hq.waitForTimeout(1000)
  console.log("Dossiers visibles :", await hq.locator("tbody tr").count())
  await shot(hq, "dossiers")

  // Premier dossier : lignes de dépenses, justificatifs et workflow.
  const firstDossier = hq.locator("tbody tr").first()
  if (await firstDossier.count()) {
    await firstDossier.click()
    await hq.waitForURL("**/dossiers/*", { timeout: 15000 })
    await hq.waitForTimeout(1200)
    console.log("Dossier - N°ORDRE :", await hq.textContent("h1"))
    console.log(
      "Dossier - lignes :",
      await hq.locator("table").first().locator("tbody tr").count(),
    )
    await shot(hq, "dossier_detail")
  }

  await hq.goto(`${BASE}/registre`, { waitUntil: "networkidle" })
  await hq.waitForTimeout(1200)
  console.log("Registre - lignes :", await hq.locator("tbody tr").count())
  console.log(
    "Registre - pagination :",
    (await hq.textContent("span.text-muted-foreground")) ?? "—",
  )
  await shot(hq, "registre")

  await hq.goto(`${BASE}/audit`, { waitUntil: "networkidle" })
  await hq.waitForTimeout(1200)
  console.log("Audit - entrées :", await hq.locator("tbody tr").count())
  await shot(hq, "audit")

  await hq.goto(`${BASE}/countries`, { waitUntil: "networkidle" })
  await hq.waitForTimeout(1000)
  console.log("Pays visibles :", await hq.locator("tbody tr").count())
  await shot(hq, "countries_hq")

  await hq.goto(`${BASE}/budgets`, { waitUntil: "networkidle" })
  await hq.waitForTimeout(1200)
  console.log("Budgets - titre :", await hq.textContent("h1"))
  console.log("Budgets - onglets :", await hq.getByRole("tab").allTextContents())
  await shot(hq, "budgets_pays")

  await hq.getByRole("tab", { name: "Enveloppes" }).click()
  await hq.waitForTimeout(600)
  await shot(hq, "budgets_enveloppes")

  await hq.getByRole("tab", { name: "Réallocations" }).click()
  await hq.waitForTimeout(600)
  await shot(hq, "budgets_reallocations")

  await hq.goto(`${BASE}/users`, { waitUntil: "networkidle" })
  await hq.waitForTimeout(1200)
  console.log("Comptes - lignes :", await hq.locator("tbody tr").count())
  await shot(hq, "users")

  // --- Parcours pays : périmètre restreint --------------------------------
  const rep = await newPage(browser)
  const repUser = await login(rep, "COUNTRY")
  console.log(`\n=== REPRÉSENTANT PAYS (${repUser}) ===`)
  console.log("Périmètre affiché :", await rep.textContent("header p.text-xs"))
  console.log("Navigation :", await rep.locator("header a").allTextContents())
  console.log("Dossiers visibles :", await rep.locator("tbody tr").count())
  await shot(rep, "dossiers_representant")

  await rep.goto(`${BASE}/countries`, { waitUntil: "networkidle" })
  await rep.waitForTimeout(1000)
  console.log("Pays visibles :", await rep.locator("tbody tr").count())
  console.log(
    "Bouton « Ajouter » visible :",
    await rep.locator('button:has-text("Ajouter")').count(),
  )
  await shot(rep, "countries_representant")

  await rep.goto(`${BASE}/budgets`, { waitUntil: "networkidle" })
  await rep.waitForTimeout(1200)
  console.log(
    "Bouton « Attribuer une enveloppe » visible :",
    await rep.locator('button:has-text("Attribuer")').count(),
  )
  await shot(rep, "budgets_representant")

  console.log("\nErreurs console :", errors.length ? errors : "aucune")
  await browser.close()
  if (errors.length) process.exitCode = 1
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
