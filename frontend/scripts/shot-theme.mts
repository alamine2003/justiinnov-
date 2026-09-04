/**
 * Revue visuelle des deux thèmes sur les écrans principaux.
 *
 *   SHOT_HQ_USER=… SHOT_HQ_PASSWORD=… SHOT_HQ_TOTP_SECRET=… \
 *   npx tsx scripts/shot-theme.mts
 */
import { chromium } from "playwright"
import { credentials, signIn } from "./login.ts"

const BASE = process.env.SHOT_BASE ?? "http://localhost:5173"
const OUT = process.env.SHOT_OUT ?? "/tmp"

const pages = [
  ["accueil", "/"],
  ["dossiers", "/dossiers"],
  ["registre", "/registre"],
  ["budgets", "/budgets"],
  ["configuration", "/configuration"],
  ["login", "/login"],
] as const

// Lève une erreur explicite si les identifiants manquent.
const compte = credentials("HQ")

const erreurs: string[] = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: "fr-FR" })
page.on("console", (message) => {
  if (message.type() === "error") erreurs.push(`[console] ${message.text()}`)
})
page.on("pageerror", (error) => erreurs.push(`[pageerror] ${String(error)}`))

async function choisirTheme(label: "Clair" | "Sombre") {
  await page.getByRole("button", { name: "Thème de l'interface" }).click()
  // Le sélecteur est un groupe radio : chaque entrée est un `menuitemradio`.
  // Le menu s'ouvre avec une transition ; cliquer avant qu'elle soit finie
  // fait rater la cible, et le menu se referme. On attend qu'il soit posé.
  const menu = page.getByRole("menu")
  await menu.waitFor({ state: "visible" })
  await page.waitForTimeout(300)
  const entree = page.getByRole("menuitemradio", { name: label, exact: true })
  await entree.waitFor({ state: "visible" })
  await entree.click()
  await menu.waitFor({ state: "hidden" })
  await page.waitForTimeout(250)
}

async function capturer(nom: string, chemin: string) {
  await page.goto(`${BASE}${chemin}`, { waitUntil: "networkidle" })
  await page.waitForTimeout(500)
  await choisirTheme("Clair")
  await page.screenshot({ path: `${OUT}/shot_theme_${nom}_clair.png` })
  await choisirTheme("Sombre")
  await page.screenshot({ path: `${OUT}/shot_theme_${nom}_sombre.png` })
}

await signIn(page, BASE, compte)

for (const [nom, chemin] of pages.slice(0, -1)) {
  await capturer(nom, chemin)
}

await page.goto(`${BASE}/login`, { waitUntil: "networkidle" })
await page.waitForTimeout(300)
await choisirTheme("Clair")
await page.screenshot({ path: `${OUT}/shot_theme_login_clair.png` })
await choisirTheme("Sombre")
await page.screenshot({ path: `${OUT}/shot_theme_login_sombre.png` })

console.log("Erreurs console :", erreurs.length ? erreurs : "aucune")
await browser.close()
if (erreurs.length) process.exitCode = 1
