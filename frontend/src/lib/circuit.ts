import type { ProofStatus, WorkflowStatus } from "@/lib/types"

/**
 * Prédicats sur les états du circuit, pendant frontal des ensembles de
 * `backend/core/statuts.py`.
 *
 * Ils servent à *présenter* — montrer un constat, un bandeau, une barre —
 * jamais à ouvrir une action : ce qui est possible reste dit par
 * `allowed_actions`. Une comparaison de statut n'a pas sa place dans un
 * composant ; `status-badge.test.tsx` y veille, et c'est ici qu'elle
 * s'écrit, une fois.
 */

export function estBrouillon(status: WorkflowStatus): boolean {
  return status === "draft"
}

/** Une ligne soumise a un constat à montrer ; un brouillon n'en a pas encore. */
export function estDeclaree(status: WorkflowStatus): boolean {
  return !estBrouillon(status)
}

/** Le siège a constaté l'absence de preuve : la branche qui remplace « justifié ». */
export function estConstatManquant(status: WorkflowStatus): boolean {
  return status === "unjustified"
}

export function estCloture(status: WorkflowStatus): boolean {
  return status === "closed"
}

/** Une pièce archivée a déjà été remplacée : on ne la remplace pas deux fois. */
export function estRemplacable(status: ProofStatus): boolean {
  return status !== "archived"
}
