import { useState, type FormEvent } from "react"
import { Loader2, PencilLine } from "lucide-react"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api"
import type { DossierDetail } from "@/lib/types"

/**
 * Bouton « Renommer » et son dialogue (décision 104).
 *
 * Le titre d'un dossier se change jusqu'à la clôture (décisions 104 et
 * 108) : il ne porte ni montant ni preuve. Clôturé, plus rien ne bouge. Le bouton n'apparaît que si le serveur le propose
 * (`rename` dans `allowed_actions` : un manager du pays par défaut).
 */
export function RenameDossier({
  dossier,
  onRename,
}: {
  dossier: DossierDetail
  onRename: (label: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  if (!dossier.allowed_actions.includes("rename")) return null

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <PencilLine className="mr-2 h-4 w-4" aria-hidden />
        {t("dossiers.renommer.bouton")}
      </Button>
      {open && (
        <RenameDialog
          numero={dossier.number}
          actuel={dossier.label}
          onOpenChange={setOpen}
          onConfirm={onRename}
        />
      )}
    </>
  )
}

/** Monté ouvert seulement : le champ repart du titre actuel à chaque ouverture. */
function RenameDialog({
  numero,
  actuel,
  onOpenChange,
  onConfirm,
}: {
  numero: string
  actuel: string
  onOpenChange: (open: boolean) => void
  onConfirm: (label: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const [label, setLabel] = useState(actuel)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!label.trim()) {
      setError(t("dossiers.renommer.titre_requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onConfirm(label.trim())
      onOpenChange(false)
    } catch (err) {
      // Le dialogue reste ouvert : le titre saisi n'est pas perdu.
      if (err instanceof ApiError && err.fields.label) setError(err.fields.label.join(" "))
      else setError(err instanceof Error ? err.message : t("dossiers.renommer.impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("dossiers.renommer.titre", { numero })}</DialogTitle>
          <DialogDescription>{t("dossiers.renommer.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="rename-label">{t("champs.label")}</Label>
            <Input
              id="rename-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              maxLength={250}
              required
            />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("dossiers.renommer.bouton")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
