import { apiGet, apiPatch, apiPost } from "@/lib/api"
import type {
  AccountUser,
  Configuration,
  Me,
  Paginated,
  PermissionMatrix,
  TotpEnrolment,
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

// ---------------------------------------------------------------------------
// Double authentification
// ---------------------------------------------------------------------------

/** Génère (ou régénère) le secret d'enrôlement ; il n'est montré qu'ici. */
export function enrolTwoFactor() {
  return apiPost<TotpEnrolment>("/me/2fa/enrol/", {})
}

/** Premier code valide : l'enrôlement est confirmé et la plateforme s'ouvre. */
export function confirmTwoFactor(code: string) {
  return apiPost<{ totp_confirmed: boolean }>("/me/2fa/confirm/", { code })
}

/** Réinitialise l'enrôlement d'un compte : son titulaire devra recommencer. */
export function resetTwoFactor(userId: number) {
  return apiPost<AccountUser>(`/users/${userId}/reset-2fa/`, {})
}

/** Chemin de l'écran de remplacement du mot de passe provisoire. */
export const PASSWORD_PATH = "/mot-de-passe"

/** Chemin de l'écran d'enrôlement de la double authentification. */
export const TOTP_PATH = "/2fa"

/**
 * Vrai quand le serveur impose la double authentification à un compte qui
 * ne l'a pas encore enrôlée. Par défaut elle est seulement proposée : un
 * serveur qui ne connaît pas `totp_required` n'impose rien.
 */
export function totpEnrolmentRequired(me: Me | null): boolean {
  return Boolean(me && me.totp_required === true && me.totp_confirmed === false)
}

/** Vrai tant que le compte n'a pas droit à l'application : mot de passe provisoire ou 2FA imposée à enrôler. */
export function platformClosed(me: Me | null): boolean {
  return Boolean(me && (me.must_change_password || totpEnrolmentRequired(me)))
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
