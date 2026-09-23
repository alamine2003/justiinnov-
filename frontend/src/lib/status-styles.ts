import type {
  AlertLevel,
  ExecutionLevel,
  ProjectStatus,
  ProofStatus,
  ReallocationStatus,
  RectificationStatus,
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

export const RECTIFICATION_STYLE: Record<RectificationStatus, string> = {
  pending: ATTENTE,
  approved: SUCCES,
  refused: DANGER,
}

export const ALERT_LEVEL_STYLE: Record<AlertLevel, string> = {
  info: INFO,
  warning: ATTENTE,
  critical: DANGER,
}

/**
 * Teinte du texte d'un taux d'exécution selon le niveau que le serveur a
 * tranché contre les seuils d'alerte. L'interface ne compare aucun taux à
 * aucun seuil : un manager et un administrateur lisent la même couleur.
 */
export const EXECUTION_LEVEL_TEXT: Record<ExecutionLevel, string> = {
  ok: "text-marque-fort",
  warning: "text-statut-attente",
  exceeded: "text-destructive",
}

// ---------------------------------------------------------------------------
// Teintes de carte
//
// Une ligne ou une demande se présente en carte, dont la bordure et le fond
// disent l'état qui attend quelqu'un : en contrôle, en attente, non justifié.
// Les cartes qui n'attendent rien gardent la bordure ordinaire.
// ---------------------------------------------------------------------------
const CARTE_NEUTRE = "border-border/60"
const CARTE_ATTENTE = "border-statut-attente/40 bg-statut-attente/5"
const CARTE_DANGER = "border-destructive/30 bg-destructive/5"

/** Bordure et fond de la carte d'une ligne de dépense, par statut du circuit. */
export const WORKFLOW_CARD_STYLE: Record<WorkflowStatus, string> = {
  draft: CARTE_NEUTRE,
  submitted: CARTE_NEUTRE,
  in_review: CARTE_ATTENTE,
  justified: CARTE_NEUTRE,
  unjustified: CARTE_DANGER,
  closed: CARTE_NEUTRE,
}

/** Bordure et fond de la carte d'une demande de réallocation, par statut. */
export const REALLOCATION_CARD_STYLE: Record<ReallocationStatus, string> = {
  pending: CARTE_ATTENTE,
  approved: CARTE_NEUTRE,
  rejected: CARTE_NEUTRE,
}

/**
 * Le flux d'une réallocation — l'enveloppe qui donne, le montant, celle qui
 * reçoit — s'éteint une fois la demande tranchée : `accent` teinte le
 * montant et la flèche, `enveloppe` les deux bouts.
 */
const FLUX_VIF = { accent: "text-marque", enveloppe: "border-border/60 bg-card" }
const FLUX_ETEINT = { accent: "text-muted-foreground", enveloppe: "border-border/40 bg-muted/30" }

export const REALLOCATION_FLOW_STYLE: Record<
  ReallocationStatus,
  { accent: string; enveloppe: string }
> = {
  pending: FLUX_VIF,
  approved: FLUX_ETEINT,
  rejected: FLUX_ETEINT,
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
  closed: ARCHIVE,
  proof_uploaded: INFO,
  proof_replaced: INFO,
  proof_incomplete: ATTENTE,
  proof_to_review: ATTENTE,
  approved: SUCCES,
  rejected: DANGER,
  downloaded: ARCHIVE,
  reopened: ATTENTE,
  rectification_requested: ATTENTE,
  rectification_decided: INFO,
  rectified: ATTENTE,
  imported: INFO,
}
