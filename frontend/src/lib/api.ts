import axios from "axios"

const TOKEN_KEY = "justi_token"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
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

  // Erreurs de validation DRF : { non_field_errors: [...], champ: [...] }
  const errors = Object.values(payload)
    .flatMap((value) => (Array.isArray(value) ? value : [value]))
    .filter((value): value is string => typeof value === "string")
  return errors.length > 0 ? errors.join(" ") : null
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearToken()
    }
    const message =
      readErrorMessage(error.response?.data) ||
      error.message ||
      "Une erreur est survenue"
    const status = error.response?.status || 0
    return Promise.reject(new ApiError(status, message))
  },
)

export async function apiGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await api.get<T>(url, { params })
  return res.data
}

export async function apiPost<T>(url: string, data: unknown): Promise<T> {
  const res = await api.post<T>(url, data)
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