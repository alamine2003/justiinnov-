import { apiGet, apiPatch, apiPost } from "@/lib/api"
import type {
  AccountUser,
  Configuration,
  Me,
  Paginated,
  PermissionMatrix,
  Role,
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

/** Un rôle tel que la matrice le décrit : libellé, siège, périmètre toujours global. */
export type RoleDeLaMatrice = PermissionMatrix["roles"][number]

/**
 * Le périmètre qu'appelle un rôle, lu sur la matrice du serveur.
 *
 * Tant que la matrice n'est pas chargée, le rôle reste inconnu : rien n'est
 * annoncé et le serveur tranche, plutôt que de recopier ici une table de
 * rôles qui divergerait. Le siège est toujours global : rien à cocher ; le
 * manager coche son pays (décision 89). Les équipes ne concernent qu'un
 * compte de pays, et seulement celles des pays cochés.
 */
export function perimetreDuRole(roleInfo: RoleDeLaMatrice | undefined) {
  const isHeadquarters = Boolean(roleInfo?.siege)
  return {
    isHeadquarters,
    alwaysGlobal: Boolean(roleInfo?.always_global),
    teamsApply: Boolean(roleInfo) && !isHeadquarters,
  }
}

/** Ce que le formulaire d'un compte a en main au moment d'enregistrer. */
export interface SaisieDuCompte {
  username: string
  firstName: string
  lastName: string
  email: string
  role: Role
  active: boolean
  countryIds: number[]
  /** Le périmètre a-t-il été touché ? Sinon il n'est pas renvoyé. */
  countriesTouched: boolean
  teamIds: number[]
  teamsTouched: boolean
  /** Vide : le mot de passe ne change pas. */
  password: string
}

/**
 * La charge utile d'une création (`editing` nul) ou d'une modification de
 * compte : seulement ce qui doit partir.
 *
 * Le périmètre n'est envoyé que s'il a été touché : un PATCH qui renvoie la
 * liste telle quelle réécrit une trace de changement pour rien.
 */
export function chargeDuCompte(
  editing: AccountUser | null,
  etat: SaisieDuCompte,
  roleInfo: RoleDeLaMatrice | undefined,
): Record<string, unknown> {
  const { alwaysGlobal, teamsApply } = perimetreDuRole(roleInfo)
  const payload: Record<string, unknown> = {
    first_name: etat.firstName,
    last_name: etat.lastName,
    email: etat.email,
    role: etat.role,
    is_active: etat.active,
  }
  // L'identifiant ne se change pas : il signe les traces du journal.
  if (!editing) payload.username = etat.username
  const roleChanged = Boolean(editing) && etat.role !== editing?.role
  if (alwaysGlobal) {
    // Aucun périmètre pour un rôle toujours global : la liste est vidée
    // si le compte en avait un, ou si le rôle vient de changer.
    if (!editing || roleChanged || editing.countries.length > 0) payload.countries = []
  } else if (!editing || etat.countriesTouched || roleChanged) {
    // Un changement de rôle renvoie le périmètre tel qu'affiché, pour
    // que le serveur le revalide contre le nouveau rôle.
    payload.countries = etat.countryIds
  }
  if (teamsApply && (!editing || etat.teamsTouched || etat.countriesTouched || roleChanged)) {
    payload.teams = etat.teamIds
  } else if (!teamsApply && editing?.teams && editing.teams.length > 0) {
    payload.teams = []
  }
  if (etat.password) payload.password = etat.password
  return payload
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

/** Règle les rôles de quelques capacités ; répond la matrice entière. */
export function updatePermissionMatrix(capabilities: Record<string, string[]>) {
  return apiPatch<PermissionMatrix>("/permissions/", { capabilities })
}

export function updateWorkflowConfiguration(data: Partial<WorkflowConfiguration>) {
  return apiPatch<WorkflowConfiguration>("/workflow-configuration/", data)
}
