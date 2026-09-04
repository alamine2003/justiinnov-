import axios, { type AxiosRequestConfig } from "axios"

const TOKEN_KEY = "justi_token"

/** Erreurs de validation, par champ. Les champs imbriqués sont aplatis (« figures.amount »). */
export type FieldErrors = Record<string, string[]>

export class ApiError extends Error {
  status: number
  fields: FieldErrors
  constructor(status: number, message: string, fields: FieldErrors = {}) {
    super(message)
    this.status = status
    this.fields = fields
    this.name = "ApiError"
  }
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

export const api = axios.create({
  baseURL: "/api",
})

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Token ${token}`
  }
  return config
})

/** Libellés des champs les plus courants, pour préfixer les messages. */
const FIELD_LABELS: Record<string, string> = {
  amount: "Montant",
  justified_amount: "Montant justifié",
  original_amount: "Montant décaissé",
  original_currency: "Devise",
  date: "Date",
  title: "Libellé",
  label: "Libellé",
  place: "Lieu",
  note: "Motif",
  reason: "Motif",
  number: "N°ORDRE",
  country: "Pays",
  countries: "Pays",
  team: "Équipe",
  project: "Projet",
  owner: "Manager",
  manager: "Manager",
  beneficiary: "Bénéficiaire",
  expense_title: "Intitulé",
  marketing_category: "Catégorie",
  payment_method: "Mode de paiement",
  username: "Identifiant",
  password: "Mot de passe",
  current_password: "Mot de passe actuel",
  new_password: "Nouveau mot de passe",
  email: "E-mail",
  role: "Rôle",
  year: "Année",
  currency: "Devise",
  timezone: "Fuseau horaire",
  code: "Code",
  name: "Nom",
  file: "Fichier",
  kind: "Type",
  source: "Enveloppe source",
  target: "Enveloppe destinataire",
  rate_to_xof: "Taux",
  valid_from: "En vigueur depuis",
  alert_thresholds: "Seuils d'alerte",
  unjustified_alert_days: "Délai d'alerte",
  unusual_expense_factor: "Facteur de dépense inhabituelle",
  default_overrun_policy: "Politique de dépassement",
}

const GENERIC_KEYS = new Set(["detail", "message", "non_field_errors"])

function fieldLabel(path: string): string {
  const last = path.split(".").pop() ?? path
  return FIELD_LABELS[last] ?? path
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
      : messages.map((message) => `${fieldLabel(path)} : ${message}`),
  )
  return errors.length > 0 ? errors.join(" ") : null
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isCancel(error)) {
      return Promise.reject(error)
    }
    const response = error.response
    if (!response) {
      // Pas de réponse HTTP : serveur arrêté, réseau coupé, proxy absent. Le
      // message d'axios (« Network Error ») ne dit rien à l'utilisateur.
      return Promise.reject(new ApiError(0, "Serveur injoignable. Vérifiez votre connexion."))
    }
    if (response.status === 401) {
      clearToken()
      unauthorizedListeners.forEach((listener) => listener())
    }
    if (
      response.status === 403 &&
      response.data &&
      typeof response.data === "object" &&
      (response.data as Record<string, unknown>).must_change_password === true
    ) {
      // Le serveur ferme la plateforme tant que le mot de passe provisoire
      // n'est pas remplacé : le profil doit être relu pour monter l'écran.
      passwordChangeListeners.forEach((listener) => listener())
    }
    const message =
      readErrorMessage(response.data) ||
      error.message ||
      "Une erreur est survenue"
    return Promise.reject(new ApiError(response.status, message, readFieldErrors(response.data)))
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

export async function apiPut<T>(url: string, data: unknown): Promise<T> {
  const res = await api.put<T>(url, data)
  return res.data
}

/** Invalide le jeton côté serveur. Un échec n'empêche pas de fermer la session locale. */
export async function apiLogout(): Promise<void> {
  await api.post("/logout/", {})
}
