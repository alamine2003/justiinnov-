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

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearToken()
    }
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      "Une erreur est survenue"
    const status = error.response?.status || 0
    return Promise.reject(new ApiError(status, message))
  },
)

function extractData<T>(detail: T): T {
  if (
    detail &&
    typeof detail === "object" &&
    "results" in detail &&
    "count" in detail
  ) {
    return detail as T
  }
  return detail
}

export async function apiGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await api.get(url, { params })
  return extractData<T>(res.data)
}

export async function apiPost<T>(url: string, data: unknown): Promise<T> {
  const res = await api.post(url, data)
  return extractData<T>(res.data)
}

export async function apiPatch<T>(url: string, data: unknown): Promise<T> {
  const res = await api.patch(url, data)
  return extractData<T>(res.data)
}

export async function apiPut<T>(url: string, data: unknown): Promise<T> {
  const res = await api.put(url, data)
  return extractData<T>(res.data)
}

export async function apiDelete(url: string): Promise<void> {
  await api.delete(url)
}