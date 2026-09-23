import type { TFunction } from "i18next"
import {
  AlertTriangle,
  ArrowRightLeft,
  FileText,
  FileWarning,
  FileX2,
  RotateCcw,
  TrendingUp,
  Undo2,
  type LucideIcon,
} from "lucide-react"
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

export const ROLES: Role[] = ["super_admin", "admin", "manager"]

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

/**
 * Le circuit dans l'ordre où il se parcourt, pour la frise du détail d'un
 * dossier. `unjustified` n'y figure pas : ce n'est pas une étape de plus,
 * c'est la branche qui remplace « justifié » quand le siège constate
 * l'absence de preuve. L'ordre suit `backend/core/statuts.py` ; ce qui est
 * *possible* à un instant donné reste dit par `allowed_actions`.
 */
export const CIRCUIT: WorkflowStatus[] = [
  "draft",
  "submitted",
  "in_review",
  "justified",
  "closed",
]

/** Rang d'un statut dans le circuit ; un constat de non-justification occupe le rang de « justifié ». */
export function circuitStep(status: WorkflowStatus): number {
  return CIRCUIT.indexOf(status === "unjustified" ? "justified" : status)
}

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
  "proof_incomplete",
  "proof_to_review",
  "approved",
  "rejected",
  "downloaded",
  "reopened",
  "rectification_requested",
  "rectification_decided",
  "rectified",
  "imported",
] as const

export function auditActionLabel(t: TFunction, action: string): string {
  return t(`libelles.audit_action.${action as (typeof AUDIT_ACTIONS)[number]}`, {
    defaultValue: action,
  })
}

/**
 * Icône d'une notification — et de l'alerte de même nature sur le Pilotage.
 * Le libellé, lui, vient du serveur (`kind_display`, `title`). Une nature
 * inconnue n'a pas d'icône : c'est le niveau qui la teinte.
 */
const NOTIFICATION_KIND_ICONS: Record<string, LucideIcon> = {
  budget_threshold: TrendingUp,
  budget_overrun: AlertTriangle,
  expense_submitted: FileText,
  expense_rejected: FileX2,
  proof_missing: FileX2,
  proof_incomplete: FileWarning,
  reallocation_requested: ArrowRightLeft,
  storage_error: AlertTriangle,
  dossier_reopened: RotateCcw,
  rectification_requested: Undo2,
  rectification_decided: Undo2,
}

export function notificationKindIcon(kind: string): LucideIcon | undefined {
  return NOTIFICATION_KIND_ICONS[kind]
}

/** Types de bénéficiaire, dans l'ordre du modèle de données. */
const BENEFICIARY_KINDS = ["prospect", "client", "supplier", "beneficiary", "other"] as const

function beneficiaryKindLabel(t: TFunction, kind: string): string {
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
