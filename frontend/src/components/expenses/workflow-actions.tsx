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
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useAuth } from "@/context/use-auth"
import type { TransitionName, WorkflowStatus } from "@/lib/types"
import { formatAmount, normalizeDecimal } from "@/lib/utils"

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

/** Données d'une transition : motif, et montant justifié pour `justify`. */
export interface TransitionPayload {
  note?: string
  justified_amount?: string
}

interface WorkflowActionsProps {
  status: WorkflowStatus
  onTransition: (action: TransitionName, payload?: TransitionPayload) => Promise<void>
  size?: "sm" | "default"
  /**
   * Masque « Soumettre » sur une ligne dont le dossier est encore un
   * brouillon. Le serveur le refuse — une ligne ne devance pas son dossier —
   * et le bouton ne menait qu'à un message d'erreur.
   */
  hideSubmit?: boolean
  /** Montant de la dépense, proposé par défaut comme montant justifié. */
  amount?: string
  currency?: string
  /** « la dépense » ou « le dossier » : les dialogues nomment ce qu'ils touchent. */
  subject?: "expense" | "dossier"
}

export function WorkflowActions({
  status,
  onTransition,
  size = "sm",
  hideSubmit = false,
  amount,
  currency,
  subject = "expense",
}: WorkflowActionsProps) {
  const { can, me } = useAuth()
  const [busy, setBusy] = useState<TransitionName | null>(null)
  const [rejecting, setRejecting] = useState(false)
  const [justifying, setJustifying] = useState(false)

  // Quand la politique impose le contrôle, une dépense soumise passe d'abord
  // « En contrôle » : proposer « Marquer justifié » mènerait à un refus.
  const requireReview = Boolean(me?.workflow?.require_review_step)

  // Soumettre relève de la saisie, les autres transitions du contrôle.
  const allowed = (AVAILABLE[status] ?? [])
    .filter((action) => !(hideSubmit && action === "submit"))
    .filter((action) => !(requireReview && status === "submitted" && action === "justify"))
    .filter((action) =>
      can(action === "submit" ? "record_expenses" : "validate_expenses"),
    )

  if (allowed.length === 0) return null

  const run = async (action: TransitionName, payload?: TransitionPayload) => {
    setBusy(action)
    try {
      await onTransition(action, payload)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {allowed.map((action) => {
        const Icon = ICONS[action]
        const isReject = action === "reject"
        const isJustify = action === "justify"
        return (
          <Button
            key={action}
            size={size}
            variant={isJustify ? "default" : "outline"}
            className={isReject ? "text-destructive hover:text-destructive" : undefined}
            disabled={busy !== null}
            onClick={() => {
              if (isReject) setRejecting(true)
              else if (isJustify) setJustifying(true)
              else void run(action)
            }}
          >
            {busy === action ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Icon className="mr-1 h-4 w-4" aria-hidden />
            )}
            {LABELS[action]}
          </Button>
        )
      })}

      {rejecting && (
        <RejectDialog
          subject={subject}
          onOpenChange={setRejecting}
          onConfirm={(note) => run("reject", { note })}
        />
      )}
      {justifying && (
        <JustifyDialog
          subject={subject}
          amount={amount}
          currency={currency}
          onOpenChange={setJustifying}
          onConfirm={(payload) => run("justify", payload)}
        />
      )}
    </div>
  )
}

const SUBJECT_LABEL = { expense: "la dépense", dossier: "le dossier" } as const

/**
 * Les dialogues ne sont montés qu'ouverts : leur état repart de zéro à chaque
 * ouverture sans effet de réinitialisation.
 */
function RejectDialog({
  subject,
  onOpenChange,
  onConfirm,
}: {
  subject: "expense" | "dossier"
  onOpenChange: (open: boolean) => void
  onConfirm: (note: string) => Promise<void>
}) {
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!note.trim()) {
      setError("Un refus doit être motivé.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onConfirm(note.trim())
      onOpenChange(false)
    } catch (err) {
      // Le dialogue reste ouvert : le motif saisi n'est pas perdu.
      setError(err instanceof Error ? err.message : "Refus impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Marquer non justifié</DialogTitle>
          <DialogDescription>
            {subject === "dossier" ? "Le dossier reste" : "La dépense reste"} au
            débit du budget : l'argent est sorti. Le motif est obligatoire et
            reste attaché à l'historique.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
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

function JustifyDialog({
  subject,
  amount,
  currency,
  onOpenChange,
  onConfirm,
}: {
  subject: "expense" | "dossier"
  amount?: string
  currency?: string
  onOpenChange: (open: boolean) => void
  onConfirm: (payload: TransitionPayload) => Promise<void>
}) {
  const [justified, setJustified] = useState(amount ?? "")
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const payload: TransitionPayload = { note: note.trim() }
    if (subject === "expense") {
      const montant = normalizeDecimal(justified)
      if (montant === null) {
        setError("Indiquez le montant justifié, en chiffres.")
        return
      }
      payload.justified_amount = montant
    }
    setSaving(true)
    setError(null)
    try {
      await onConfirm(payload)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Justification impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Marquer justifié</DialogTitle>
          <DialogDescription>
            {subject === "expense"
              ? "Le montant justifié est celui que les pièces attestent. Le serveur calcule l'écart avec la dépense."
              : "Toutes les lignes du dossier seront marquées justifiées."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          {subject === "expense" && (
            <div className="grid gap-2">
              <Label htmlFor="justify-amount">
                Montant justifié {currency ? `(${currency})` : ""}
              </Label>
              <Input
                id="justify-amount"
                inputMode="decimal"
                value={justified}
                onChange={(e) => setJustified(e.target.value)}
                required
              />
              {amount && (
                <p className="text-xs text-muted-foreground">
                  Dépense déclarée : {formatAmount(amount, currency)}. Par
                  défaut, tout est justifié.
                </p>
              )}
            </div>
          )}
          <div className="grid gap-2">
            <Label htmlFor="justify-note">
              Note {subject === "expense" ? "(obligatoire si le montant est partiel)" : "(facultative)"}
            </Label>
            <Textarea
              id="justify-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Facture n° 123 pour 80 %, reste sans pièce…"
            />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Annuler
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
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

export { SUBJECT_LABEL as WORKFLOW_SUBJECT_LABEL }
