import { api, apiGet, apiPost } from "@/lib/api"
import type {
  AppNotification,
  Breakdown,
  Dashboard,
  Paginated,
} from "@/lib/types"

// ---------------------------------------------------------------------------
// Pilotage
// ---------------------------------------------------------------------------
export function fetchDashboard(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Dashboard>("/dashboard/", params, signal)
}

export function fetchBreakdown(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Breakdown>("/dashboard/breakdown/", params, signal)
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

/** Formats des exports tabulaires ; le rapport n'existe qu'en PDF. */
export const TABULAR_FORMATS = ["xlsx", "csv", "docx"] as const
export type TabularFormat = (typeof TABULAR_FORMATS)[number]

/** Routes d'export, telles que le serveur les expose : `exports/<kind>`. */
export type ExportKind =
  | `expenses.${TabularFormat}`
  | `reconciliation.${TabularFormat}`
  | "report.pdf"

/** Famille d'un export : ce qu'il contient, indépendamment du format. */
export type ExportFamily = "expenses" | "reconciliation" | "report"

const EXPORT_NAMES: Record<ExportFamily, string> = {
  expenses: "depenses",
  reconciliation: "rapprochement",
  report: "rapport",
}

/** Période d'un export : l'exercice, éventuellement borné à un mois, et le pays. */
export interface ExportPeriod {
  year: number
  /** 1 à 12 ; absent ou `null` pour l'exercice entier. */
  month?: number | null
  country?: number | "" | null
}

export function exportFamily(kind: ExportKind): ExportFamily {
  return kind.slice(0, kind.lastIndexOf(".")) as ExportFamily
}

/** Extension du fichier, déduite de la route : le serveur et le nom du fichier disent la même chose. */
export function exportExtension(kind: ExportKind): string {
  return kind.slice(kind.lastIndexOf(".") + 1)
}

/** Paramètres de requête d'un export ; `month` et `country` ne partent que s'ils sont fixés. */
export function exportParams(period: ExportPeriod): Record<string, unknown> {
  const params: Record<string, unknown> = { year: period.year }
  if (period.month) params.month = period.month
  if (period.country !== undefined && period.country !== null && period.country !== "") {
    params.country = period.country
  }
  return params
}

/** Nom du fichier téléchargé : `depenses-2026.xlsx`, `rapprochement-2026-03.csv`. */
export function exportFilename(kind: ExportKind, period: ExportPeriod): string {
  const mois = period.month ? `-${String(period.month).padStart(2, "0")}` : ""
  return `${EXPORT_NAMES[exportFamily(kind)]}-${period.year}${mois}.${exportExtension(kind)}`
}

/**
 * Télécharge un export.
 *
 * Comme les justificatifs, ces fichiers exigent le jeton : ils ne peuvent pas
 * être obtenus par un simple lien.
 */
export async function downloadExport(kind: ExportKind, period: ExportPeriod) {
  const response = await api.get(`/exports/${kind}`, {
    params: exportParams(period),
    responseType: "blob",
  })
  const url = URL.createObjectURL(response.data as Blob)
  const link = document.createElement("a")
  link.href = url
  link.download = exportFilename(kind, period)
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Révoquée après coup : le navigateur n'a pas forcément fini de lire le blob.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

// ---------------------------------------------------------------------------
// Import
// ---------------------------------------------------------------------------

/** Une ligne du classeur refusée, avec son numéro et le motif du serveur. */
export interface ImportError {
  ligne?: number
  motif?: string
}

export interface ImportResult {
  lignes_creees: number
  equipes_creees: number
  managers_crees: number
  /** Chaîne brute ou `{ligne, motif}` : les deux formes sont affichées. */
  erreurs: (ImportError | string)[]
  dry_run: boolean
  [extra: string]: unknown
}

/**
 * Importe un classeur de dépenses. `country` est obligatoire pour un
 * classeur sans colonne PAYS ; `dryRun` simule sans rien écrire.
 */
export function importExpenses(
  file: File,
  options: { country?: number | ""; dryRun: boolean },
) {
  const form = new FormData()
  form.append("file", file)
  const params: Record<string, unknown> = {}
  if (options.dryRun) params.dry_run = "true"
  if (options.country !== undefined && options.country !== "") params.country = options.country
  return apiPost<ImportResult>("/imports/expenses.xlsx", form, { params })
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------
export function fetchNotifications(params?: Record<string, unknown>) {
  return apiGet<Paginated<AppNotification>>("/notifications/", params)
}

export function fetchUnreadCount() {
  return apiGet<{ unread: number }>("/notifications/unread_count/")
}

export function markNotificationRead(id: number) {
  return apiPost<AppNotification>(`/notifications/${id}/read/`, {})
}

export function markAllNotificationsRead() {
  return apiPost<{ marked: number }>("/notifications/read-all/", {})
}
