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
import type { ExpenseTransitionName, Schema, TransitionName } from "@/lib/types"
import { formatAmount, normalizeDecimal } from "@/lib/utils"

/** Transitions que ce composant sait proposer ; « rouvrir » a son propre bouton. */
const TRANSITIONS: TransitionName[] = ["submit", "review", "justify", "reject", "close"]

function isTransition(value: string): value is TransitionName {
  return (TRANSITIONS as string[]).includes(value)
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

interface CommonProps {
  size?: "sm" | "default"
  /** Montant de la dépense, proposé par défaut comme montant justifié. */
  amount?: string
  currency?: string
  /**
   * Transitions calculées par le serveur pour le demandeur (`allowed_actions`
   * de la ligne ou du dossier) : rôle, état, quatre yeux, politique du
   * circuit. L'interface n'en recopie aucune règle ; elle propose ce que le
   * serveur accepterait.
   */
  allowedActions: Schema<"TransitionEnum">[]
  /**
   * Reçoit l'échec d'une action directe (mise en contrôle, clôture…), pour
   * l'afficher dans l'alerte de la page ; sans lui, l'erreur s'affiche ici.
   * Les dialogues affichent eux-mêmes leur refus, sans passer par là.
   */
  onError?: (message: string) => void
}

/** « la dépense » ou « le dossier » : les dialogues nomment ce qu'ils touchent, et une ligne ne se soumet jamais seule. */
type WorkflowActionsProps = CommonProps &
  (
    | {
        subject?: "expense"
        onTransition: (action: ExpenseTransitionName, payload?: TransitionPayload) => Promise<void>
      }
    | {
        subject: "dossier"
        onTransition: (action: TransitionName, payload?: TransitionPayload) => Promise<void>
      }
  )

export function WorkflowActions(props: WorkflowActionsProps) {
  const { size = "sm", amount, currency, allowedActions, onError } = props
  const subject = props.subject ?? "expense"
  const { t } = useTranslation()
  const [busy, setBusy] = useState<TransitionName | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rejecting, setRejecting] = useState(false)
  const [justifying, setJustifying] = useState(false)

  // Le dossier emporte ses lignes : c'est lui qu'on soumet, jamais une ligne
  // seule. Une action inconnue de l'interface est ignorée.
  const allowed = allowedActions
    .filter(isTransition)
    .filter((action) => subject === "dossier" || action !== "submit")

  if (allowed.length === 0) return null

  /** Lance une transition ; l'appelant décide de l'affichage de l'échec. */
  const run = async (action: TransitionName, payload?: TransitionPayload) => {
    setBusy(action)
    try {
      if (props.subject === "dossier") {
        await props.onTransition(action, payload)
      } else if (action !== "submit") {
        await props.onTransition(action, payload)
      }
    } finally {
      setBusy(null)
    }
  }

  /** Action sans dialogue : l'échec est affiché une fois, ici ou dans la page. */
  const runDirect = (action: TransitionName) => {
    setError(null)
    run(action).catch((e: unknown) => {
      const message = e instanceof Error ? e.message : t("erreurs.action_impossible")
      if (onError) onError(message)
      else setError(message)
    })
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
              else runDirect(action)
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
      {!onError && <FormError>{error}</FormError>}

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
