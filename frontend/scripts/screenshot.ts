import { chromium } from "playwright"

const BASE = "http://localhost:5173"

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

  // Capturer les erreurs de console / réseau
  const errors: string[] = []
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`[console] ${m.text()}`)
  })
  page.on("pageerror", (e) => errors.push(`[pageerror] ${String(e)}`))

  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" })
  await page.screenshot({ path: "/tmp/shot_login.png", fullPage: false })

  await page.fill("#username", "admin")
  await page.fill("#password", "admin123")
  await page.click("button[type=submit]")
  await page.waitForURL("**/countries", { timeout: 15000 })
  await page.waitForTimeout(1500)

  console.log("LISTE - Titre:", await page.textContent("h1"))
  console.log("LISTE - Rows:", await page.locator("tbody tr").count())
  await page.screenshot({ path: "/tmp/shot_countries.png", fullPage: false })

  await page.goto(`${BASE}/countries/1`, { waitUntil: "networkidle" })
  await page.waitForTimeout(1200)
  console.log("DETAIL - Nom:", await page.textContent("h1"))
  console.log("DETAIL - Tabs:", await page.getByRole("tab").allTextContents())
  await page.screenshot({ path: "/tmp/shot_detail_equipes.png", fullPage: false })

  await page.getByRole("tab", { name: "Historique" }).click()
  await page.waitForTimeout(800)
  console.log("HISTORIQUE - Entrées:", await page.locator("tbody tr").count())
  console.log("HISTORIQUE - Cards:", await page.locator("div.card, [class*=rounded-lg][class*=border]").count() - 2)
  await page.screenshot({ path: "/tmp/shot_detail_historique.png", fullPage: false })

  console.log("ERRORS:", errors.length ? errors : "aucune")
  await browser.close()
  console.log("OK")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})