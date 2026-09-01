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
export function fetchDashboard(params?: Record<string, unknown>) {
  return apiGet<Dashboard>("/dashboard/", params)
}

export function fetchBreakdown(params?: Record<string, unknown>) {
  return apiGet<Breakdown>("/dashboard/breakdown/", params)
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------
export type ExportKind = "expenses.xlsx" | "reconciliation.xlsx" | "report.pdf"

const EXPORT_NAMES: Record<ExportKind, string> = {
  "expenses.xlsx": "depenses",
  "reconciliation.xlsx": "rapprochement",
  "report.pdf": "rapport",
}

/**
 * Télécharge un export.
 *
 * Comme les justificatifs, ces fichiers exigent le jeton : ils ne peuvent pas
 * être obtenus par un simple lien.
 */
export async function downloadExport(
  kind: ExportKind,
  params: Record<string, unknown>,
) {
  const response = await api.get(`/exports/${kind}`, {
    params,
    responseType: "blob",
  })
  const url = URL.createObjectURL(response.data as Blob)
  const extension = kind.endsWith(".pdf") ? "pdf" : "xlsx"
  const link = document.createElement("a")
  link.href = url
  link.download = `${EXPORT_NAMES[kind]}-${params.year ?? ""}.${extension}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
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
