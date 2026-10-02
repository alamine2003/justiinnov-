import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { PROJECT_STYLE, PROOF_STYLE, STATUS_TONES, WORKFLOW_STYLE } from "@/lib/status-styles"
import { projectStatusLabel, proofStatusLabel, workflowLabel } from "@/lib/labels"
import type { Project, ProjectStatus, ProofStatus, WorkflowStatus } from "@/lib/types"

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

/**
 * Type d'un projet (décision 100) : son libellé, contourné, puisque ce
 * n'est pas un état. Deux cas se signalent : le projet « Historique » où
 * la reprise a rangé les dossiers d'avant la 2.0 (archivé), et un projet
 * d'avant la 2.0 que le siège doit encore typer (en attente). Les deux
 * viennent du serveur (`is_historical`, `a_typer`), l'écran n'en déduit rien.
 */
export function ProjectKindBadge({
  project,
}: {
  project: Pick<Project, "kind_display" | "is_historical" | "a_typer">
}) {
  const { t } = useTranslation()
  if (project.is_historical) {
    return <Badge className={STATUS_TONES.ARCHIVE}>{t("projets.historique")}</Badge>
  }
  if (project.a_typer) {
    return <Badge className={STATUS_TONES.ATTENTE}>{t("projets.a_typer")}</Badge>
  }
  return <Badge variant="outline">{project.kind_display}</Badge>
}
