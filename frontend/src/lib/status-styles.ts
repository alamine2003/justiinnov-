import type {
  AlertLevel,
  ProjectStatus,
  ProofStatus,
  ReallocationStatus,
  WorkflowStatus,
} from "@/lib/types"

/**
 * Correspondance statut → teinte. Liste close : voir « Couleurs de statut »
 * dans DESIGN.md. Un nouveau statut s'ajoute ici, jamais dans la page qui
 * l'affiche.
 */
const SUCCES = "bg-statut-succes text-statut-succes-foreground hover:bg-statut-succes"
const ATTENTE = "bg-statut-attente text-statut-attente-foreground hover:bg-statut-attente"
const INFO = "bg-statut-info text-statut-info-foreground hover:bg-statut-info"
const NEUTRE = "bg-statut-neutre text-statut-neutre-foreground hover:bg-statut-neutre"
const ARCHIVE = "bg-statut-archive text-statut-archive-foreground hover:bg-statut-archive"
const DANGER = "bg-destructive text-destructive-foreground hover:bg-destructive"

export const STATUS_TONES = { SUCCES, ATTENTE, INFO, NEUTRE, ARCHIVE, DANGER } as const

export const WORKFLOW_STYLE: Record<WorkflowStatus, string> = {
  draft: NEUTRE,
  submitted: INFO,
  in_review: ATTENTE,
  justified: SUCCES,
  unjustified: DANGER,
  closed: ARCHIVE,
}

export const PROOF_STYLE: Record<ProofStatus, string> = {
  received: INFO,
  incomplete: ATTENTE,
  to_review: ATTENTE,
  validated: SUCCES,
  rejected: DANGER,
  archived: ARCHIVE,
}

export const PROJECT_STYLE: Record<ProjectStatus, string> = {
  planned: NEUTRE,
  active: SUCCES,
  on_hold: ATTENTE,
  completed: INFO,
}

export const REALLOCATION_STYLE: Record<ReallocationStatus, string> = {
  pending: ATTENTE,
  approved: SUCCES,
  rejected: DANGER,
}

export const ALERT_LEVEL_STYLE: Record<AlertLevel, string> = {
  info: INFO,
  warning: ATTENTE,
  critical: DANGER,
}

/** Actions du journal d'audit et de l'historique du référentiel. */
export const ACTION_STYLE: Record<string, string> = {
  created: SUCCES,
  updated: INFO,
  reassigned: ATTENTE,
  deactivated: ARCHIVE,
  reactivated: SUCCES,
  deleted: ARCHIVE,
  submitted: INFO,
  reviewed: ATTENTE,
  justified: SUCCES,
  unjustified: DANGER,
  approved: SUCCES,
  rejected: DANGER,
  downloaded: ARCHIVE,
}
