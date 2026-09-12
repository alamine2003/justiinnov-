import { useState, type FormEvent } from "react"
import { Check, Loader2, Undo2, X } from "lucide-react"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { approveRectification, refuseRectification } from "@/lib/expenses"
import { RECTIFICATION_STYLE, WORKFLOW_STYLE } from "@/lib/status-styles"
import type { Rectification } from "@/lib/types"
import { formatAmount, formatDate } from "@/lib/utils"

interface RectificationPanelProps {
  rows: Rectification[]
  currency?: string
  /** Rappelé après une décision : la ligne et le dossier ont pu changer. */
  onDecided: () => Promise<void>
}

/**
 * Demandes de rectification d'un dossier, en attente ou tranchées.
 *
 * Le serveur dit qui tranche (`can_decide`) : demande encore en attente,
 * rôle décideur, pas son auteur. Approuvée, la ligne revient en contrôle et
 * le dossier la suit ; refusée, le constat tient. Rien ici ne recopie ces
 * règles : le panneau affiche et appelle.
 */
export function RectificationPanel({ rows, currency, onDecided }: RectificationPanelProps) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [refusing, setRefusing] = useState<Rectification | null>(null)

  if (rows.length === 0) return null

  const handleApprove = async (row: Rectification) => {
    setBusyId(row.id)
    setError(null)
    try {
      await approveRectification(row.id)
      await onDecided()
    } catch (e) {
      setError(e instanceof Error ? e.message : t("depenses.rectification.approbation_impossible"))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold">{t("depenses.rectification.panneau_titre")}</h3>
        <p className="text-xs text-muted-foreground">
          {t("depenses.rectification.panneau_description")}
        </p>
      </div>

      <FormError>{error}</FormError>

      <div className="overflow-x-auto rounded-lg border border-border/60">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">{t("champs.label")}</TableHead>
              <TableHead scope="col">{t("depenses.rectification.colonnes.constat")}</TableHead>
              <TableHead scope="col">{t("depenses.rectification.colonnes.motif")}</TableHead>
              <TableHead scope="col">{t("commun.statut")}</TableHead>
              <TableHead scope="col" className="text-right">{t("commun.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <p className="font-medium">{row.expense_title}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(row.created_at)}
                    {row.requested_by &&
                      ` · ${t("depenses.rectification.par", { auteur: row.requested_by })}`}
                  </p>
                </TableCell>
                <TableCell>
                  <Badge className={WORKFLOW_STYLE[row.previous_status]}>
                    {row.previous_status_display}
                  </Badge>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t("depenses.rectification.justifie_avant", {
                      montant: formatAmount(row.previous_justified_amount, currency),
                    })}
                  </p>
                </TableCell>
                <TableCell className="max-w-xs">
                  <p className="line-clamp-3 text-xs text-muted-foreground">{row.motif}</p>
                  {row.decision_note && (
                    <p className="line-clamp-2 text-xs italic text-muted-foreground">
                      {t("depenses.rectification.decision", { note: row.decision_note })}
                    </p>
                  )}
                </TableCell>
                <TableCell>
                  <Badge className={RECTIFICATION_STYLE[row.status]}>{row.status_display}</Badge>
                  {row.decided_by && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t("depenses.rectification.par", { auteur: row.decided_by })}
                    </p>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  {row.can_decide && (
                    <>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("depenses.rectification.approuver")}
                        disabled={busyId === row.id}
                        onClick={() => void handleApprove(row)}
                      >
                        {busyId === row.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Check className="h-4 w-4 text-statut-succes" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("depenses.rectification.refuser")}
                        className="text-destructive hover:text-destructive"
                        disabled={busyId === row.id}
                        onClick={() => setRefusing(row)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {refusing && (
        <RefuseDialog
          key={refusing.id}
          rectification={refusing}
          onClose={() => setRefusing(null)}
          onRefused={onDecided}
        />
      )}
    </div>
  )
}

function RefuseDialog({
  rectification,
  onClose,
  onRefused,
}: {
  rectification: Rectification
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
      setError(t("depenses.rectification.motif_refus_requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await refuseRectification(rectification.id, note.trim())
      await onRefused()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : t("depenses.rectification.refus_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t("depenses.rectification.refus_titre", { titre: rectification.expense_title })}
          </DialogTitle>
          <DialogDescription>{t("depenses.rectification.refus_description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="rectification-refus-note">
              {t("depenses.rectification.motif_refus")}
            </Label>
            <Textarea
              id="rectification-refus-note"
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
                  <Undo2 className="mr-2 h-4 w-4" aria-hidden />
                )}
                {t("depenses.rectification.refuser")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
