import type { TFunction } from "i18next"
import { RotateCcw, type LucideIcon } from "lucide-react"
import type {
  AlertLevel,
  OverrunPolicy,
  ProjectStatus,
  ProofStatus,
  Role,
  WorkflowStatus,
} from "@/lib/types"
import type { Theme } from "@/lib/theme"

/**
 * Libellés des valeurs codées, dans la langue de l'interface.
 *
 * Chaque fonction reçoit le `t` du composant appelant (`useTranslation`),
 * pour que l'écran se rafraîchisse au changement de langue. Le libellé du
 * serveur (`*_display`) reste prioritaire quand la page l'a : ces tables ne
 * sont qu'un repli, pour ne jamais afficher une clé brute.
 */

export const ROLES: Role[] = ["super_admin", "admin", "df", "dm", "manager"]

export function roleLabel(t: TFunction, role: Role): string {
  return t(`libelles.roles.${role}`)
}

export const WORKFLOW_STATUSES: WorkflowStatus[] = [
  "draft",
  "submitted",
  "in_review",
  "justified",
  "unjustified",
  "closed",
]

export function workflowLabel(t: TFunction, status: WorkflowStatus): string {
  return t(`libelles.workflow.${status}`, { defaultValue: status })
}

export const PROOF_STATUSES: ProofStatus[] = [
  "received",
  "incomplete",
  "to_review",
  "validated",
  "rejected",
  "archived",
]

export function proofStatusLabel(t: TFunction, status: ProofStatus): string {
  return t(`libelles.piece_statut.${status}`, { defaultValue: status })
}

/** Types de justificatif, dans l'ordre du modèle de données. */
export const PROOF_KINDS = ["receipt", "invoice", "discharge", "deliverable", "other"] as const

export function proofKindLabel(t: TFunction, kind: string): string {
  return t(`libelles.piece_type.${kind as (typeof PROOF_KINDS)[number]}`, { defaultValue: kind })
}

export const PROJECT_STATUSES: ProjectStatus[] = ["planned", "active", "on_hold", "completed"]

export function projectStatusLabel(t: TFunction, status: ProjectStatus): string {
  return t(`libelles.projet_statut.${status}`, { defaultValue: status })
}

export const OVERRUN_POLICIES: OverrunPolicy[] = ["block", "warn", "approval"]

export function overrunPolicyLabel(t: TFunction, policy: OverrunPolicy): string {
  return t(`libelles.depassement.${policy}`, { defaultValue: policy })
}

export function alertLevelLabel(t: TFunction, level: AlertLevel): string {
  return t(`libelles.alerte_niveau.${level}`, { defaultValue: level })
}

/**
 * Actions proposées au filtre du journal. Les entrées affichent le libellé du
 * serveur (`action_display`) ; cette liste ne sert qu'à proposer les valeurs
 * avant qu'une entrée soit chargée.
 */
export const AUDIT_ACTIONS = [
  "created",
  "updated",
  "deleted",
  "submitted",
  "reviewed",
  "justified",
  "unjustified",
  "closed",
  "proof_uploaded",
  "proof_replaced",
  "approved",
  "rejected",
  "downloaded",
  "reopened",
] as const

export function auditActionLabel(t: TFunction, action: string): string {
  return t(`libelles.audit_action.${action as (typeof AUDIT_ACTIONS)[number]}`, {
    defaultValue: action,
  })
}

/** Icône d'une action du journal quand elle en mérite une ; les autres restent un badge. */
export const AUDIT_ACTION_ICONS: Partial<Record<(typeof AUDIT_ACTIONS)[number], LucideIcon>> = {
  reopened: RotateCcw,
}

/**
 * Types de notification connus de l'interface. Le libellé du serveur
 * (`kind_display`) reste prioritaire ; ces tables ne servent qu'à l'icône et
 * au repli.
 */
export const NOTIFICATION_KINDS = ["dossier_reopened"] as const

export function notificationKindLabel(t: TFunction, kind: string): string {
  return t(`libelles.notification_type.${kind as (typeof NOTIFICATION_KINDS)[number]}`, {
    defaultValue: kind,
  })
}

export const NOTIFICATION_KIND_ICONS: Partial<
  Record<(typeof NOTIFICATION_KINDS)[number], LucideIcon>
> = {
  dossier_reopened: RotateCcw,
}

export function notificationKindIcon(kind: string): LucideIcon | undefined {
  return NOTIFICATION_KIND_ICONS[kind as (typeof NOTIFICATION_KINDS)[number]]
}

/** Types de bénéficiaire, dans l'ordre du modèle de données. */
export const BENEFICIARY_KINDS = ["prospect", "client", "supplier", "beneficiary", "other"] as const

export function beneficiaryKindLabel(t: TFunction, kind: string): string {
  return t(`libelles.beneficiaire_type.${kind as (typeof BENEFICIARY_KINDS)[number]}`, {
    defaultValue: kind,
  })
}

export function beneficiaryKinds(t: TFunction): { value: string; label: string }[] {
  return BENEFICIARY_KINDS.map((value) => ({ value, label: beneficiaryKindLabel(t, value) }))
}

export function themeLabel(t: TFunction, theme: Theme): string {
  return t(`libelles.theme.${theme}`)
}
