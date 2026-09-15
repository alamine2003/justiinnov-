import { useState, type FormEvent } from "react"
import { Loader2, Lock, RotateCcw } from "lucide-react"
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
import { REQUEST_REOPENING, type DossierDetail } from "@/lib/types"

interface RequestReopeningProps {
  dossier: DossierDetail
  onRequest: (motif: string) => Promise<void>
}

/**
 * Bouton « Demander la réouverture » d'un dossier et son dialogue.
 *
 * Le pays a soumis, et s'aperçoit d'une erreur : il ne rouvre pas
 * lui-même — seul le siège le fait — mais il le demande, motif à l'appui,
 * et un administrateur décide. Le bouton n'apparaît que lorsque le serveur
 * accepterait la demande : il le dit dans `allowed_actions` (droit,
 * dossier soumis ou en contrôle, aucune ligne constatée, aucune demande
 * déjà en attente).
 */
export function RequestReopening({ dossier, onRequest }: RequestReopeningProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  if (!(dossier.allowed_actions as string[]).includes(REQUEST_REOPENING)) return null

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <RotateCcw className="mr-2 h-4 w-4" aria-hidden />
        {t("dossiers.demande_reouverture.bouton")}
      </Button>
      {open && (
        <ReopeningDialog dossier={dossier} onOpenChange={setOpen} onConfirm={onRequest} />
      )}
    </>
  )
}

/** Monté ouvert seulement : l'état repart de zéro à chaque ouverture. */
function ReopeningDialog({
  dossier,
  onOpenChange,
  onConfirm,
}: {
  dossier: DossierDetail
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
      setMotifError(t("dossiers.demande_reouverture.motif_requis"))
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
      // sur le motif s'affiche sous lui ; un refus sur le dossier (déjà une
      // demande, état qui ne se rouvre pas, ligne constatée) en tête.
      if (err instanceof ApiError) {
        if (err.fields.motif) setMotifError(err.fields.motif.join(" "))
        const general = [
          ...(err.fields.dossier ?? []),
          ...(err.fields.status ?? []),
          ...(err.fields.expenses ?? []),
          ...(err.fields.non_field_errors ?? []),
        ]
        if (general.length > 0) setError(general.join(" "))
        else if (!err.fields.motif) setError(err.message)
      } else {
        setError(err instanceof Error ? err.message : t("dossiers.demande_reouverture.impossible"))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t("dossiers.demande_reouverture.titre", { numero: dossier.number })}
          </DialogTitle>
          <DialogDescription>{t("dossiers.demande_reouverture.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="reouverture-motif">{t("dossiers.demande_reouverture.motif")}</Label>
            <Textarea
              id="reouverture-motif"
              value={motif}
              onChange={(e) => setMotif(e.target.value)}
              placeholder={t("dossiers.demande_reouverture.motif_placeholder")}
              aria-invalid={Boolean(motifError)}
              aria-describedby={motifError ? "reouverture-motif-error" : undefined}
              required
            />
            {motifError && (
              <p id="reouverture-motif-error" role="alert" className="text-xs text-destructive">
                {motifError}
              </p>
            )}
          </div>
          {/* Là où la réouverture s'arrête commence la rectification : le
              dialogue le dit avant que le serveur ne le refuse. */}
          <p className="flex items-start gap-2 rounded-lg border border-border/60 bg-muted/40 p-3 text-xs text-muted-foreground">
            <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            {t("dossiers.demande_reouverture.verrou")}
          </p>
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
                {t("dossiers.demande_reouverture.envoyer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
