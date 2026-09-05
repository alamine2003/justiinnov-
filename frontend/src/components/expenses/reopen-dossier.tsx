import { useState, type FormEvent } from "react"
import { Loader2, RotateCcw } from "lucide-react"
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
import type { DossierDetail } from "@/lib/types"

interface ReopenDossierProps {
  dossier: DossierDetail
  onReopen: (note: string) => Promise<void>
}

/**
 * Bouton « Rouvrir » et son dialogue.
 *
 * Le siège seul rouvre un dossier déclaré ; le pays est prévenu et devra le
 * soumettre à nouveau. Le bouton n'apparaît que lorsque le serveur
 * accepterait : il le dit dans `allowed_actions` (droit, état du dossier,
 * lignes déjà justifiées ou clôturées).
 */
export function ReopenDossier({ dossier, onReopen }: ReopenDossierProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  if (!dossier.allowed_actions.includes("reopen")) return null

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <RotateCcw className="mr-2 h-4 w-4" aria-hidden />
        {t("dossiers.reouverture.rouvrir")}
      </Button>
      {open && (
        <ReopenDialog
          numero={dossier.number}
          onOpenChange={setOpen}
          onConfirm={onReopen}
        />
      )}
    </>
  )
}

/** Monté ouvert seulement : l'état repart de zéro à chaque ouverture. */
function ReopenDialog({
  numero,
  onOpenChange,
  onConfirm,
}: {
  numero: string
  onOpenChange: (open: boolean) => void
  onConfirm: (note: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const [note, setNote] = useState("")
  const [noteError, setNoteError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!note.trim()) {
      setNoteError(t("dossiers.reouverture.motif_requis"))
      return
    }
    setSaving(true)
    setError(null)
    setNoteError(null)
    try {
      await onConfirm(note.trim())
      onOpenChange(false)
    } catch (err) {
      // Le dialogue reste ouvert : le motif saisi n'est pas perdu. Les
      // refus du serveur sont rendus là où ils portent : sous le motif, ou
      // en tête quand ils concernent les lignes ou le statut du dossier.
      if (err instanceof ApiError) {
        if (err.fields.note) setNoteError(err.fields.note.join(" "))
        const general = [
          ...(err.fields.expenses ? [t("dossiers.reouverture.lignes_bloquantes")] : []),
          ...(err.fields.expenses ?? []),
          ...(err.fields.status ?? []),
          ...(err.fields.non_field_errors ?? []),
        ]
        if (general.length > 0) setError(general.join(" "))
        else if (!err.fields.note) setError(err.message)
      } else {
        setError(err instanceof Error ? err.message : t("dossiers.reouverture.impossible"))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("dossiers.reouverture.titre", { numero })}</DialogTitle>
          <DialogDescription>{t("dossiers.reouverture.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="reopen-motif">{t("dossiers.reouverture.motif")}</Label>
            <Textarea
              id="reopen-motif"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t("dossiers.reouverture.motif_placeholder")}
              aria-invalid={Boolean(noteError)}
              aria-describedby={noteError ? "reopen-motif-error" : undefined}
              required
            />
            {noteError && (
              <p id="reopen-motif-error" role="alert" className="text-xs text-destructive">
                {noteError}
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
                  <RotateCcw className="mr-2 h-4 w-4" aria-hidden />
                )}
                {t("dossiers.reouverture.rouvrir")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
