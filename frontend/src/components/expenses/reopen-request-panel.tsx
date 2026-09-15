import { useState, type FormEvent } from "react"
import { Check, Loader2, RotateCcw, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
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
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { approveReopening, refuseReopening } from "@/lib/expenses"
import { RECTIFICATION_STYLE } from "@/lib/status-styles"
import type { ReopenRequest } from "@/lib/types"
import { cn, formatDate } from "@/lib/utils"

interface ReopenRequestPanelProps {
  rows: ReopenRequest[]
  /** Rappelé après une décision : le dossier a pu revenir au brouillon. */
  onDecided: () => Promise<void>
}

/**
 * Demandes de réouverture d'un dossier, en attente ou tranchées.
 *
 * Le serveur dit qui tranche (`can_decide`) : demande encore en attente,
 * rôle décideur, pas son auteur. Approuvée, le dossier et ses lignes
 * reviennent au brouillon — c'est la réouverture ordinaire, par la
 * demande du pays ; refusée, le dossier reste tel quel. Rien ici ne
 * recopie ces règles : le panneau affiche et appelle. Les statuts d'une
 * demande sont ceux d'une rectification (mêmes teintes).
 */
export function ReopenRequestPanel({ rows, onDecided }: ReopenRequestPanelProps) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [refusing, setRefusing] = useState<ReopenRequest | null>(null)

  if (rows.length === 0) return null

  const handleApprove = async (row: ReopenRequest) => {
    setBusyId(row.id)
    setError(null)
    try {
      await approveReopening(row.id)
      await onDecided()
    } catch (e) {
      setError(
        e instanceof Error ? e.message : t("dossiers.demande_reouverture.approbation_impossible"),
      )
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold">{t("dossiers.demande_reouverture.panneau_titre")}</h3>
        <p className="text-xs text-muted-foreground">
          {t("dossiers.demande_reouverture.panneau_description")}
        </p>
      </div>

      <FormError>{error}</FormError>

      <ul className="space-y-3" aria-label={t("dossiers.demande_reouverture.panneau_titre")}>
        {rows.map((row) => (
          <li
            key={row.id}
            className={cn(
              "rounded-lg border p-3",
              row.status === "pending" ? "border-statut-attente/60 bg-statut-attente/5" : "border-border/60 bg-card",
            )}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  <RotateCcw className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                  {t("dossiers.demande_reouverture.etat_avant", {
                    statut: row.previous_status_display.toLocaleLowerCase(),
                  })}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {formatDate(row.created_at)}
                  {row.requested_by &&
                    ` · ${t("dossiers.demande_reouverture.par", { auteur: row.requested_by })}`}
                </p>
              </div>
              <Badge className={RECTIFICATION_STYLE[row.status]}>{row.status_display}</Badge>
            </div>
            {/* Un seul nœud de texte : voir `reallocations.tsx`. */}
            <p className="mt-2 text-sm italic text-muted-foreground">{`« ${row.motif} »`}</p>
            {row.decision_note && (
              <p className="mt-1 text-xs italic text-muted-foreground">
                {t("dossiers.demande_reouverture.decision", { note: row.decision_note })}
                {row.decided_by &&
                  ` — ${t("dossiers.demande_reouverture.par", { auteur: row.decided_by })}`}
              </p>
            )}
            {row.can_decide && (
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  disabled={busyId === row.id}
                  onClick={() => void handleApprove(row)}
                >
                  {busyId === row.id ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="mr-1 h-4 w-4" aria-hidden />
                  )}
                  {t("dossiers.demande_reouverture.approuver")}
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={busyId === row.id}
                  onClick={() => setRefusing(row)}
                >
                  <X className="mr-1 h-4 w-4" aria-hidden />
                  {t("dossiers.demande_reouverture.refuser")}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {refusing && (
        <RefuseDialog
          key={refusing.id}
          demande={refusing}
          onClose={() => setRefusing(null)}
          onRefused={onDecided}
        />
      )}
    </div>
  )
}

function RefuseDialog({
  demande,
  onClose,
  onRefused,
}: {
  demande: ReopenRequest
  onClose: () => void
  onRefused: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!note.trim()) {
      setError(t("dossiers.demande_reouverture.motif_refus_requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await refuseReopening(demande.id, note.trim())
      await onRefused()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : t("dossiers.demande_reouverture.refus_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t("dossiers.demande_reouverture.refus_titre", { numero: demande.dossier_number })}
          </DialogTitle>
          <DialogDescription>{t("dossiers.demande_reouverture.refus_description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="reouverture-refus-note">
              {t("dossiers.demande_reouverture.motif_refus")}
            </Label>
            <Textarea
              id="reouverture-refus-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              required
            />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={onClose}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" variant="destructive" disabled={saving} className="ml-2">
                {saving ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <X className="mr-2 h-4 w-4" aria-hidden />
                )}
                {t("dossiers.demande_reouverture.refuser")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
