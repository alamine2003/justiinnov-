import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { PROJECT_STYLE, PROOF_STYLE, WORKFLOW_STYLE } from "@/lib/status-styles"
import { projectStatusLabel, proofStatusLabel, workflowLabel } from "@/lib/labels"
import type { ProjectStatus, ProofStatus, WorkflowStatus } from "@/lib/types"

/**
 * Le libellé vient du serveur (`status_display`) quand la page l'a ; la table
 * locale (`lib/labels.ts`) ne sert que de repli, pour ne jamais afficher une
 * clé brute.
 */
export function StatusBadge({
  status,
  label,
}: {
  status: WorkflowStatus
  label?: string
}) {
  const { t } = useTranslation()
  return (
    <Badge className={WORKFLOW_STYLE[status] ?? "bg-secondary"}>
      {label ?? workflowLabel(t, status)}
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
  const { t } = useTranslation()
  return (
    <Badge className={PROOF_STYLE[status] ?? "bg-secondary"}>
      {label ?? proofStatusLabel(t, status)}
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
  const { t } = useTranslation()
  return (
    <Badge className={PROJECT_STYLE[status] ?? "bg-secondary"}>
      {label ?? projectStatusLabel(t, status)}
    </Badge>
  )
}
