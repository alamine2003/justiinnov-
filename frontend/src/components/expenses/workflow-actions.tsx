import { useState, type FormEvent } from "react"
import { Check, Loader2, Play, Search, Send, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
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

function transitionLabel(t: TFunction, action: TransitionName): string {
  switch (action) {
    case "submit":
      return t("depenses.circuit.soumettre")
    case "review":
      return t("depenses.circuit.prendre_en_controle")
    case "justify":
      return t("depenses.circuit.marquer_justifie")
    case "reject":
      return t("depenses.circuit.marquer_non_justifie")
    case "close":
      return t("depenses.circuit.cloturer")
  }
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
  const { t } = useTranslation()
  const { can, me } = useAuth()
  const [busy, setBusy] = useState<TransitionName | null>(null)
  const [rejecting, setRejecting] = useState(false)
  const [justifying, setJustifying] = useState(false)

  // Quand la politique impose le contrôle, une dépense soumise passe d'abord
  // « En contrôle » : proposer « Marquer justifié » mènerait à un refus.
  const requireReview = Boolean(me?.workflow?.require_review_step)

  // Soumettre relève de la saisie (le manager), la mise en contrôle du DM,
  // le constat — justifier, refuser, clôturer — du DF. Un serveur qui ne
  // distingue pas encore la mise en contrôle la range avec le constat.
  const canReview = me?.permissions?.review_expenses ?? can("validate_expenses")
  const permitted = (action: TransitionName): boolean => {
    if (action === "submit") return can("record_expenses")
    if (action === "review") return canReview
    return can("validate_expenses")
  }
  const allowed = (AVAILABLE[status] ?? [])
    .filter((action) => !(hideSubmit && action === "submit"))
    .filter((action) => !(requireReview && status === "submitted" && action === "justify"))
    .filter(permitted)

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
            {transitionLabel(t, action)}
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
  const { t } = useTranslation()
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!note.trim()) {
      setError(t("depenses.rejet.motif_requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onConfirm(note.trim())
      onOpenChange(false)
    } catch (err) {
      // Le dialogue reste ouvert : le motif saisi n'est pas perdu.
      setError(err instanceof Error ? err.message : t("depenses.rejet.impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("depenses.circuit.marquer_non_justifie")}</DialogTitle>
          <DialogDescription>
            {subject === "dossier"
              ? t("depenses.rejet.description_dossier")
              : t("depenses.rejet.description_depense")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="reject-motif">{t("depenses.rejet.motif")}</Label>
            <Textarea
              id="reject-motif"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t("depenses.rejet.motif_placeholder")}
              required
            />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={saving}
                className="ml-2"
              >
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("commun.confirmer")}
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
  const { t } = useTranslation()
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
        setError(t("depenses.justification.montant_requis"))
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
      setError(err instanceof Error ? err.message : t("depenses.justification.impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("depenses.circuit.marquer_justifie")}</DialogTitle>
          <DialogDescription>
            {subject === "expense"
              ? t("depenses.justification.description_depense")
              : t("depenses.justification.description_dossier")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          {subject === "expense" && (
            <div className="grid gap-2">
              <Label htmlFor="justify-amount">
                {currency
                  ? t("depenses.justification.montant_devise", { devise: currency })
                  : t("depenses.justification.montant")}
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
                  {t("depenses.justification.declaree", {
                    montant: formatAmount(amount, currency),
                  })}
                </p>
              )}
            </div>
          )}
          <div className="grid gap-2">
            <Label htmlFor="justify-note">
              {subject === "expense"
                ? t("depenses.justification.note_partiel")
                : t("depenses.justification.note_facultative")}
            </Label>
            <Textarea
              id="justify-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t("depenses.justification.note_placeholder")}
            />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("commun.confirmer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
