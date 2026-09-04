/**
 * Connexion des scripts de capture, double authentification comprise.
 *
 * Les identifiants viennent de l'environnement, jamais du dépôt :
 *
 *   SHOT_<PREFIXE>_USER, SHOT_<PREFIXE>_PASSWORD et, pour un compte enrôlé,
 *   SHOT_<PREFIXE>_TOTP_SECRET (secret base32, celui du QR d'enrôlement).
 *
 * Le code est calculé à la volée et saisi d'emblée ; si le serveur le
 * réclame malgré tout (code périmé), il est recalculé et présenté à nouveau.
 */
import { generate } from "otplib"
import type { Page } from "playwright"

export interface Credentials {
  prefix: string
  user: string
  password: string
  totpSecret?: string
}

export function credentials(prefix: string): Credentials {
  const user = process.env[`SHOT_${prefix}_USER`]
  const password = process.env[`SHOT_${prefix}_PASSWORD`]
  if (!user || !password) {
    throw new Error(
      `SHOT_${prefix}_USER et SHOT_${prefix}_PASSWORD doivent être définis.`,
    )
  }
  return { prefix, user, password, totpSecret: process.env[`SHOT_${prefix}_TOTP_SECRET`] }
}

const HORS_CONNEXION = (url: URL) => !url.pathname.startsWith("/login")

/** Remplit le formulaire, code de double authentification compris. */
export async function signIn(page: Page, base: string, account: Credentials) {
  await page.goto(`${base}/login`, { waitUntil: "networkidle" })
  await page.fill("#username", account.user)
  await page.fill("#password", account.password)
  // Le champ du code est toujours présent : un compte enrôlé se connecte en
  // une seule fois, sans le détour par un refus du serveur.
  if (account.totpSecret) {
    await page.fill("#totp-code", await generate({ secret: account.totpSecret }))
  }
  await page.click("button[type=submit]")

  try {
    await page.waitForURL(HORS_CONNEXION, { timeout: 15000 })
    return
  } catch {
    // Le serveur a refusé : soit le code a expiré entre le calcul et l'envoi
    // (fenêtre de trente secondes), soit le compte n'a pas de secret connu.
  }
  if (!account.totpSecret) {
    throw new Error(
      `La connexion de ${account.user} n'a pas abouti : définissez ` +
        `SHOT_${account.prefix}_TOTP_SECRET si le compte est enrôlé.`,
    )
  }
  const bouton = page.locator("button[type=submit]")
  await bouton.waitFor({ state: "visible" })
  await page.fill("#totp-code", await generate({ secret: account.totpSecret }))
  await bouton.click()
  await page.waitForURL(HORS_CONNEXION, { timeout: 15000 })
}
