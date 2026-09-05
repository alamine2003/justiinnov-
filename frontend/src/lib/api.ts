import axios, { type AxiosRequestConfig } from "axios"
import i18next from "i18next"

const TOKEN_KEY = "justi_token"

/** Erreurs de validation, par champ. Les champs imbriqués sont aplatis (« figures.amount »). */
export type FieldErrors = Record<string, string[]>

export class ApiError extends Error {
  status: number
  fields: FieldErrors
  /** Corps brut de la réponse, pour les indicateurs qui ne sont pas des champs (`totp_required`). */
  data: unknown
  constructor(status: number, message: string, fields: FieldErrors = {}, data: unknown = null) {
    super(message)
    this.status = status
    this.fields = fields
    this.data = data
    this.name = "ApiError"
  }
}

/** Vrai quand la réponse porte un indicateur booléen donné (`{"totp_required": true}`). */
export function hasFlag(error: unknown, flag: string): boolean {
  return (
    error instanceof ApiError &&
    typeof error.data === "object" &&
    error.data !== null &&
    (error.data as Record<string, unknown>)[flag] === true
  )
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

// ---------------------------------------------------------------------------
// Événements de session
//
// Le client HTTP ne connaît ni React ni le routeur. Il signale seulement ce
// qui lui arrive ; `AuthProvider` s'y abonne pour vider l'état et rediriger.
// ---------------------------------------------------------------------------
type Listener = () => void

const unauthorizedListeners = new Set<Listener>()
const passwordChangeListeners = new Set<Listener>()
const totpSetupListeners = new Set<Listener>()

/** Abonne à la perte de session (401). Renvoie la fonction de désabonnement. */
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

/** Abonne au refus « mot de passe provisoire » (403 `must_change_password`). */
export function onPasswordChangeRequired(listener: Listener): () => void {
  passwordChangeListeners.add(listener)
  return () => passwordChangeListeners.delete(listener)
}

/** Abonne au refus « double authentification à enrôler » (403 `totp_setup_required`). */
export function onTotpSetupRequired(listener: Listener): () => void {
  totpSetupListeners.add(listener)
  return () => totpSetupListeners.delete(listener)
}

export const api = axios.create({
  baseURL: "/api",
})

// Langue demandée au serveur pour ses libellés (`*_display`, messages
// d'erreur, alertes). Tenue à jour par `i18n/index.ts` à chaque changement.
let apiLanguage = "fr"

export function setApiLanguage(language: string) {
  apiLanguage = language
}

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Token ${token}`
  }
  config.headers["Accept-Language"] = apiLanguage
  return config
})

/** Champs dont le libellé est connu, pour préfixer les messages (`champs.*` des traductions). */
const KNOWN_FIELDS = new Set([
  "amount", "justified_amount", "original_amount", "original_currency", "date",
  "title", "label", "place", "note", "reason", "number", "country", "countries",
  "team", "teams", "project", "owner", "manager", "beneficiary", "expense_title",
  "marketing_category", "payment_method", "username", "password",
  "current_password", "new_password", "email", "role", "year", "currency",
  "timezone", "code", "name", "file", "kind", "source", "target", "rate_to_xof",
  "valid_from", "alert_thresholds", "unjustified_alert_days",
  "unusual_expense_factor", "default_overrun_policy", "language",
  "expenses", "proofs", "status", "dossier", "replaces", "budget", "created_by",
  "is_active",
])

const GENERIC_KEYS = new Set(["detail", "message", "non_field_errors"])

function fieldLabel(path: string): string {
  const last = path.split(".").pop() ?? path
  return KNOWN_FIELDS.has(last) ? i18next.t(`champs.${last}`, { defaultValue: path }) : path
}

/**
 * Aplatit les erreurs de validation DRF en carte champ → messages.
 *
 * DRF imbrique les erreurs des sous-objets ({ figures: { amount: [...] } }) ;
 * un formulaire a besoin d'un chemin plat pour retrouver son champ.
 */
export function readFieldErrors(data: unknown, prefix = ""): FieldErrors {
  if (!data || typeof data !== "object" || Array.isArray(data)) return {}
  const fields: FieldErrors = {}
  for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === "string") {
      fields[path] = [value]
    } else if (Array.isArray(value)) {
      const messages = value.filter((item): item is string => typeof item === "string")
      if (messages.length > 0) fields[path] = messages
      // Une liste d'objets (erreurs par ligne) est aplatie avec son index.
      value.forEach((item, index) => {
        if (item && typeof item === "object") {
          Object.assign(fields, readFieldErrors(item, `${path}.${index}`))
        }
      })
    } else if (value && typeof value === "object") {
      Object.assign(fields, readFieldErrors(value, path))
    }
  }
  return fields
}

/** Extrait un message lisible d'une réponse d'erreur DRF.
 *
 * Une réponse peut aussi être une page d'erreur HTML — 404 hors des routes de
 * l'API, 502 du proxy. La recracher telle quelle déverserait la page entière
 * dans l'interface : on lui préfère le message générique de l'appelant.
 */
export function readErrorMessage(data: unknown): string | null {
  if (typeof data === "string") {
    const texte = data.trim()
    if (!texte || texte.startsWith("<")) return null
    return texte
  }
  if (!data || typeof data !== "object") return null

  const payload = data as Record<string, unknown>
  if (typeof payload.detail === "string") return payload.detail
  if (typeof payload.message === "string") return payload.message

  // Erreurs de validation DRF : { non_field_errors: [...], champ: [...] }.
  // Le libellé du champ précède le message, sinon « Ce champ est
  // obligatoire. » ne dit pas lequel.
  const errors = Object.entries(readFieldErrors(payload)).flatMap(([path, messages]) =>
    GENERIC_KEYS.has(path)
      ? messages
      : messages.map((message) => `${fieldLabel(path)}${i18next.t("commun.separateur_libelle")}${message}`),
  )
  return errors.length > 0 ? errors.join(" ") : null
}

/**
 * Corps d'une réponse d'erreur, lisible même quand la requête attendait un
 * fichier.
 *
 * Un téléchargement (`responseType: "blob"`) reçoit aussi ses erreurs en
 * `Blob` : sans cette lecture, un refus du serveur s'affichait « Request
 * failed with status code 403 » au lieu de son message.
 */
async function readErrorBody(data: unknown): Promise<unknown> {
  if (typeof Blob === "undefined" || !(data instanceof Blob)) return data
  try {
    const texte = await readBlobText(data)
    if (data.type.includes("json")) return JSON.parse(texte) as unknown
    return texte
  } catch {
    return null
  }
}

/** Texte d'un Blob ; `FileReader` en secours pour les environnements sans `Blob.text()`. */
function readBlobText(blob: Blob): Promise<string> {
  if (typeof blob.text === "function") return blob.text()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ""))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (axios.isCancel(error)) {
      return Promise.reject(error)
    }
    const response = error.response
    if (!response) {
      // Pas de réponse HTTP : serveur arrêté, réseau coupé, proxy absent. Le
      // message d'axios (« Network Error ») ne dit rien à l'utilisateur.
      return Promise.reject(new ApiError(0, i18next.t("erreurs.injoignable")))
    }
    response.data = await readErrorBody(response.data)
    if (response.status === 401) {
      clearToken()
      unauthorizedListeners.forEach((listener) => listener())
    }
    if (response.status === 403 && response.data && typeof response.data === "object") {
      const flags = response.data as Record<string, unknown>
      // Le serveur ferme la plateforme tant que le mot de passe provisoire
      // n'est pas remplacé, puis tant que la double authentification n'est
      // pas enrôlée : le profil doit être relu pour monter l'écran voulu.
      if (flags.must_change_password === true) {
        passwordChangeListeners.forEach((listener) => listener())
      }
      if (flags.totp_setup_required === true) {
        totpSetupListeners.forEach((listener) => listener())
      }
    }
    const message =
      readErrorMessage(response.data) ||
      error.message ||
      i18next.t("erreurs.generique")
    return Promise.reject(
      new ApiError(response.status, message, readFieldErrors(response.data), response.data),
    )
  },
)

/** Vrai pour une requête annulée par un `AbortController` : ce n'est pas une erreur. */
export function isCancelled(error: unknown): boolean {
  return axios.isCancel(error)
}

export async function apiGet<T>(
  url: string,
  params?: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<T> {
  const res = await api.get<T>(url, { params, signal })
  return res.data
}

export async function apiPost<T>(
  url: string,
  data: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const res = await api.post<T>(url, data, config)
  return res.data
}

export async function apiPatch<T>(url: string, data: unknown): Promise<T> {
  const res = await api.patch<T>(url, data)
  return res.data
}

/** Invalide le jeton côté serveur. Un échec n'empêche pas de fermer la session locale. */
export async function apiLogout(): Promise<void> {
  await api.post("/logout/", {})
}
