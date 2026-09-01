import { apiGet, apiPatch, apiPost } from "@/lib/api"
import type { AccountUser, Me, Paginated } from "@/lib/types"

export function fetchMe() {
  return apiGet<Me>("/me/")
}

export function changePassword(currentPassword: string, newPassword: string) {
  return apiPost<void>("/me/password/", {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export function fetchUsers(params?: Record<string, unknown>) {
  return apiGet<Paginated<AccountUser>>("/users/", params)
}

export function createUser(data: unknown) {
  return apiPost<AccountUser>("/users/", data)
}

export function updateUser(id: number, data: unknown) {
  return apiPatch<AccountUser>(`/users/${id}/`, data)
}
