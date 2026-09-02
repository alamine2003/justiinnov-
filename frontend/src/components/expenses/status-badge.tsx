import { Badge } from "@/components/ui/badge"
import {
  PROOF_STATUS_LABELS,
  WORKFLOW_LABELS,
  type ProofStatus,
  type WorkflowStatus,
} from "@/lib/types"

const WORKFLOW_STYLE: Record<WorkflowStatus, string> = {
  draft: "bg-slate-500 hover:bg-slate-500",
  submitted: "bg-blue-500 hover:bg-blue-500",
  in_review: "bg-amber-500 hover:bg-amber-500",
  justified: "bg-emerald-500 hover:bg-emerald-500",
  unjustified: "bg-destructive hover:bg-destructive",
  closed: "bg-zinc-600 hover:bg-zinc-600",
}

export function StatusBadge({ status }: { status: WorkflowStatus }) {
  return (
    <Badge className={WORKFLOW_STYLE[status] ?? "bg-secondary"}>
      {WORKFLOW_LABELS[status] ?? status}
    </Badge>
  )
}

const PROOF_STYLE: Record<ProofStatus, string> = {
  received: "bg-blue-500 hover:bg-blue-500",
  incomplete: "bg-amber-500 hover:bg-amber-500",
  to_review: "bg-amber-500 hover:bg-amber-500",
  validated: "bg-emerald-500 hover:bg-emerald-500",
  rejected: "bg-destructive hover:bg-destructive",
  archived: "bg-zinc-500 hover:bg-zinc-500",
}

export function ProofStatusBadge({ status }: { status: ProofStatus }) {
  return (
    <Badge className={PROOF_STYLE[status] ?? "bg-secondary"}>
      {PROOF_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}
