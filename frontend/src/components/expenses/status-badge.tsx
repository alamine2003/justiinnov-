import { Badge } from "@/components/ui/badge"
import { PROJECT_STYLE, PROOF_STYLE, WORKFLOW_STYLE } from "@/lib/status-styles"
import {
  PROJECT_STATUS_LABELS,
  PROOF_STATUS_LABELS,
  WORKFLOW_LABELS,
  type ProjectStatus,
  type ProofStatus,
  type WorkflowStatus,
} from "@/lib/types"

/**
 * Le libellé vient du serveur (`status_display`) quand la page l'a ; la table
 * locale ne sert que de repli, pour ne jamais afficher une clé brute.
 */
export function StatusBadge({
  status,
  label,
}: {
  status: WorkflowStatus
  label?: string
}) {
  return (
    <Badge className={WORKFLOW_STYLE[status] ?? "bg-secondary"}>
      {label ?? WORKFLOW_LABELS[status] ?? status}
    </Badge>
  )
}

export function ProofStatusBadge({
  status,
  label,
}: {
  status: ProofStatus
  label?: string
}) {
  return (
    <Badge className={PROOF_STYLE[status] ?? "bg-secondary"}>
      {label ?? PROOF_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

export function ProjectStatusBadge({
  status,
  label,
}: {
  status: ProjectStatus
  label?: string
}) {
  return (
    <Badge className={PROJECT_STYLE[status] ?? "bg-secondary"}>
      {label ?? PROJECT_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}
