import { useState, type FormEvent } from "react"
import { Loader2, Undo2 } from "lucide-react"
import { useTranslation } from "react-i18next"
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
import { ApiError } from "@/lib/api"
import { REQUEST_RECTIFICATION, type Expense } from "@/lib/types"

interface RequestRectificationProps {
  expense: Expense
  size?: "sm" | "default"
  onRequest: (motif: string) => Promise<void>
}

/**
 * Bouton « Rectifier » d'une ligne et son dialogue.
 *
 * Seconde exception à l'irréversibilité : une ligne justifiée ou clôturée
 * l'a été à tort. N'importe qui peut le dire — avec un motif — ; un
 * administrateur décide, et la ligne ne bouge qu'à sa décision. Le bouton
 * n'apparaît que lorsque le serveur accepterait la demande : il le dit
 * dans `allowed_actions` (droit, état de la ligne, aucune demande déjà en
 * attente).
 */
export function RequestRectification({ expense, size = "sm", onRequest }: RequestRectificationProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  if (!(expense.allowed_actions as string[]).includes(REQUEST_RECTIFICATION)) return null

  return (
    <>
      <Button size={size} variant="outline" onClick={() => setOpen(true)}>
        <Undo2 className="mr-1 h-4 w-4" aria-hidden />
        {t("depenses.rectification.rectifier")}
      </Button>
      {open && (
        <RectificationDialog
          expense={expense}
          onOpenChange={setOpen}
          onConfirm={onRequest}
        />
      )}
    </>
  )
}

/** Monté ouvert seulement : l'état repart de zéro à chaque ouverture. */
function RectificationDialog({
  expense,
  onOpenChange,
  onConfirm,
}: {
  expense: Expense
  onOpenChange: (open: boolean) => void
  onConfirm: (motif: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const [motif, setMotif] = useState("")
  const [motifError, setMotifError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!motif.trim()) {
      setMotifError(t("depenses.rectification.motif_requis"))
      return
    }
    setSaving(true)
    setError(null)
    setMotifError(null)
    try {
      await onConfirm(motif.trim())
      onOpenChange(false)
    } catch (err) {
      // Le dialogue reste ouvert : le motif saisi n'est pas perdu. Un refus
      // sur le motif s'affiche sous lui ; un refus sur la ligne (déjà une
      // demande en attente, état qui ne se rectifie pas) en tête.
      if (err instanceof ApiError) {
        if (err.fields.motif) setMotifError(err.fields.motif.join(" "))
        const general = [
          ...(err.fields.expense ?? []),
          ...(err.fields.status ?? []),
          ...(err.fields.non_field_errors ?? []),
        ]
        if (general.length > 0) setError(general.join(" "))
        else if (!err.fields.motif) setError(err.message)
      } else {
        setError(err instanceof Error ? err.message : t("depenses.rectification.impossible"))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("depenses.rectification.titre", { titre: expense.title })}</DialogTitle>
          <DialogDescription>{t("depenses.rectification.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="rectification-motif">{t("depenses.rectification.motif")}</Label>
            <Textarea
              id="rectification-motif"
              value={motif}
              onChange={(e) => setMotif(e.target.value)}
              placeholder={t("depenses.rectification.motif_placeholder")}
              aria-invalid={Boolean(motifError)}
              aria-describedby={motifError ? "rectification-motif-error" : undefined}
              required
            />
            {motifError && (
              <p id="rectification-motif-error" role="alert" className="text-xs text-destructive">
                {motifError}
              </p>
            )}
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Undo2 className="mr-2 h-4 w-4" aria-hidden />
                )}
                {t("depenses.rectification.envoyer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
