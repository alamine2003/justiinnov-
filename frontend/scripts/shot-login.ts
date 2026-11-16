/**
 * Capture la page de connexion, en grand écran et en mobile, et la passe
 * au contrôle d'accessibilité.
 *
 *   SHOT_OUT=/tmp npx tsx scripts/shot-login.ts
 */
import { chromium } from "playwright"
import { controlerAccessibilite } from "./accessibilite.ts"

const BASE = process.env.SHOT_BASE ?? "http://localhost:5173"
const OUT = process.env.SHOT_OUT ?? "/tmp"

const FORMATS = [
  { nom: "login", width: 1440, height: 900 },
  { nom: "login_mobile", width: 420, height: 860 },
]

async function main() {
  const browser = await chromium.launch()
  const errors: string[] = []

  for (const { nom, width, height } of FORMATS) {
    // Un contexte à soi : axe y ouvre sa page de synthèse (`accessibilite.ts`).
    const contexte = await browser.newContext({ viewport: { width, height }, locale: "fr-FR" })
    const page = await contexte.newPage()
    page.on("pageerror", (e) => errors.push(String(e)))
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text())
    })
    await page.goto(`${BASE}/login`, { waitUntil: "networkidle" })
    await page.waitForTimeout(700)
    await page.screenshot({ path: `${OUT}/shot_${nom}.png` })
    errors.push(...(await controlerAccessibilite(page, nom)))
    await contexte.close()
  }

  console.log("Erreurs console et accessibilité :", errors.length ? errors : "aucune")
  await browser.close()
  if (errors.length) process.exitCode = 1
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
