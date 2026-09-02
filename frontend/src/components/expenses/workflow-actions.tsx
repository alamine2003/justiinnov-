import { useState, type FormEvent } from "react"
import { Check, Loader2, Play, Search, Send, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useAuth } from "@/context/auth"
import type { TransitionName, WorkflowStatus } from "@/lib/types"

/** Transitions possibles depuis chaque état — reflète `expenses.workflow`. */
const AVAILABLE: Record<WorkflowStatus, TransitionName[]> = {
  draft: ["submit"],
  submitted: ["review", "justify", "reject"],
  in_review: ["justify", "reject"],
  // Une dépense non justifiée ne revient pas au brouillon : seule une preuve
  // déposée après coup peut encore la justifier.
  unjustified: ["justify"],
  justified: ["close"],
  closed: [],
}

const LABELS: Record<TransitionName, string> = {
  submit: "Soumettre",
  review: "Prendre en contrôle",
  justify: "Marquer justifié",
  reject: "Marquer non justifié",
  close: "Clôturer",
}

const ICONS = {
  submit: Send,
  review: Search,
  justify: Check,
  reject: X,
  close: Play,
}

interface WorkflowActionsProps {
  status: WorkflowStatus
  onTransition: (action: TransitionName, note?: string) => Promise<void>
  size?: "sm" | "default"
}

export function WorkflowActions({
  status,
  onTransition,
  size = "sm",
}: WorkflowActionsProps) {
  const { can } = useAuth()
  const [busy, setBusy] = useState<TransitionName | null>(null)
  const [rejecting, setRejecting] = useState(false)

  // Soumettre relève de la saisie, les autres transitions du contrôle.
  const allowed = (AVAILABLE[status] ?? []).filter((action) =>
    can(action === "submit" ? "record_expenses" : "validate_expenses"),
  )

  if (allowed.length === 0) return null

  const run = async (action: TransitionName, note?: string) => {
    setBusy(action)
    try {
      await onTransition(action, note)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {allowed.map((action) => {
        const Icon = ICONS[action]
        const isReject = action === "reject"
        return (
          <Button
            key={action}
            size={size}
            variant={isReject ? "outline" : action === "justify" ? "default" : "outline"}
            className={isReject ? "text-destructive hover:text-destructive" : undefined}
            disabled={busy !== null}
            onClick={() => (isReject ? setRejecting(true) : run(action))}
          >
            {busy === action ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Icon className="mr-1 h-4 w-4" />
            )}
            {LABELS[action]}
          </Button>
        )
      })}

      <RejectDialog
        open={rejecting}
        onOpenChange={setRejecting}
        onConfirm={async (note) => {
          await run("reject", note)
          setRejecting(false)
        }}
      />
    </div>
  )
}

function RejectDialog({
  open,
  onOpenChange,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (note: string) => Promise<void>
}) {
  const [note, setNote] = useState("")
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await onConfirm(note)
      setNote("")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Marquer non justifié</DialogTitle>
          <DialogDescription>
            La dépense reste au débit du budget : l'argent est sorti. Le motif
            est obligatoire et reste attaché à l'historique.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="reject-motif">Motif du refus</Label>
            <Textarea
              id="reject-motif"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Facture illisible, montant incohérent…"
              required
            />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Annuler
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={saving}
                className="ml-2"
              >
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Confirmer
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
