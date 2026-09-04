import { apiGet, apiPatch, apiPost } from "@/lib/api"
import type {
  AccountUser,
  Configuration,
  Me,
  Paginated,
  PermissionMatrix,
  WorkflowConfiguration,
} from "@/lib/types"

export function fetchMe() {
  return apiGet<Me>("/me/")
}

/** Renvoie le nouveau jeton : l'ancien est révoqué avec l'ancien mot de passe. */
export function changePassword(currentPassword: string, newPassword: string) {
  return apiPost<{ token?: string }>("/me/password/", {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export function fetchUsers(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<AccountUser>>("/users/", params, signal)
}

export function createUser(data: unknown) {
  return apiPost<AccountUser>("/users/", data)
}

export function updateUser(id: number, data: unknown) {
  return apiPatch<AccountUser>(`/users/${id}/`, data)
}

// ---------------------------------------------------------------------------
// Back-office
// ---------------------------------------------------------------------------
export function fetchConfiguration() {
  return apiGet<Configuration>("/configuration/")
}

export function fetchPermissionMatrix() {
  return apiGet<PermissionMatrix>("/permissions/")
}

export function updateWorkflowConfiguration(data: Partial<WorkflowConfiguration>) {
  return apiPatch<WorkflowConfiguration>("/workflow-configuration/", data)
}
