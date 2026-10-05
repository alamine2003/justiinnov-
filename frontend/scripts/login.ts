/**
 * Connexion des scripts de capture, double authentification comprise.
 *
 * Les identifiants viennent de l'environnement, jamais du dépôt :
 *
 *   SHOT_<PREFIXE>_USER, SHOT_<PREFIXE>_PASSWORD et, pour un compte enrôlé,
 *   SHOT_<PREFIXE>_TOTP_SECRET (secret base32, celui du QR d'enrôlement).
 *
 * La connexion se fait en deux temps, comme à l'écran : identifiant et mot
 * de passe, puis le code — calculé à la volée — si le serveur le réclame ;
 * un code périmé entre-temps est recalculé et présenté à nouveau.
 */
import { generate } from "otplib"
import type { ConsoleMessage, Page } from "playwright"

/**
 * Le premier temps d'une connexion enrôlée répond `400 totp_required` :
 * voulu, mais le navigateur le journalise comme une erreur. Les scripts, qui
 * échouent sur toute erreur de console, écartent celle-là et elle seule —
 * ce statut, sur cette adresse.
 */
export function estLeRefusAttenduDuCode(message: ConsoleMessage): boolean {
  return message.text().includes("status of 400") && message.location().url.endsWith("/api/token-auth/")
}

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

/** Fenêtre TOTP (RFC 6238) : trente secondes. */
const PAS_TOTP_MS = 30_000
/** Dernier pas de temps consommé par secret : un code accepté ne se rejoue pas. */
const codesConsommes = new Map<string, number>()

/**
 * Calcule le code courant en évitant de rejouer celui d'une connexion
 * précédente : le serveur refuse un code déjà accepté (anti-rejeu). Si le
 * même secret a servi dans la fenêtre courante, on attend la suivante.
 */
async function codeFrais(secret: string) {
  const pas = Math.floor(Date.now() / PAS_TOTP_MS)
  if (codesConsommes.get(secret) === pas) {
    const attente = (pas + 1) * PAS_TOTP_MS - Date.now() + 500
    await new Promise((resolve) => setTimeout(resolve, attente))
  }
  codesConsommes.set(secret, Math.floor(Date.now() / PAS_TOTP_MS))
  return generate({ secret })
}

/**
 * Se connecte en deux temps, comme une personne : identifiant et mot de
 * passe, puis le code si le serveur le demande (le champ n'apparaît qu'à ce
 * moment-là, compte enrôlé).
 */
export async function signIn(page: Page, base: string, account: Credentials) {
  await page.goto(`${base}/login`, { waitUntil: "networkidle" })
  await page.fill("#username", account.user)
  await page.fill("#password", account.password)
  await page.click("button[type=submit]")

  const champCode = page.locator("#totp-code")
  // Chaque attente rattrape son propre échec : la perdante expire après
  // coup, et un rejet sans gestionnaire arrêterait le script.
  const issue = await Promise.race([
    page.waitForURL(HORS_CONNEXION, { timeout: 15000 }).then(() => "connecte" as const, () => null),
    champCode.waitFor({ state: "visible", timeout: 15000 }).then(() => "code" as const, () => null),
  ])
  if (issue === "connecte") return
  if (issue === null) throw new Error(`La connexion de ${account.user} n'a pas abouti.`)
  if (!account.totpSecret) {
    throw new Error(
      `La connexion de ${account.user} demande un code : définissez ` +
        `SHOT_${account.prefix}_TOTP_SECRET pour ce compte enrôlé.`,
    )
  }
  // Un code peut expirer entre le calcul et l'envoi (fenêtre de trente
  // secondes) : un second essai, avec un code frais, suffit.
  for (let essai = 0; essai < 2; essai++) {
    await champCode.fill(await codeFrais(account.totpSecret))
    await page.click("button[type=submit]")
    try {
      await page.waitForURL(HORS_CONNEXION, { timeout: 15000 })
      return
    } catch {
      if (essai === 1) throw new Error(`Le code de ${account.user} a été refusé deux fois.`)
    }
  }
}
