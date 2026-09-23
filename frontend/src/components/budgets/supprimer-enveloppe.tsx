import { useState } from "react"
import { Loader2, Trash2 } from "lucide-react"
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
import { ApiError } from "@/lib/api"
import type { Budget } from "@/lib/types"

/**
 * Bouton « Supprimer » d'une enveloppe et son dialogue de confirmation.
 *
 * Seule une enveloppe qui n'a jamais servi se supprime, et seule la
 * direction le peut (décision 91) : le bouton n'apparaît que si le serveur
 * le dit (`can_delete`). Une enveloppe qui a servi se désactive depuis son
 * formulaire.
 */
export function SupprimerEnveloppe({
  budget,
  nom,
  onDelete,
}: {
  budget: Budget
  /** Ce que l'écran appelle cette enveloppe : le pays, ou la sous-enveloppe. */
  nom: string
  onDelete: (budget: Budget) => Promise<void>
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  if (!budget.can_delete) return null

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        aria-label={t("budgets.suppression.bouton_aria", { enveloppe: nom })}
        className="text-destructive hover:text-destructive"
        onClick={() => setOpen(true)}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
      {open && (
        <ConfirmationDialog budget={budget} nom={nom} onOpenChange={setOpen} onConfirm={onDelete} />
      )}
    </>
  )
}

/** Monté ouvert seulement : l'état repart de zéro à chaque ouverture. */
function ConfirmationDialog({
  budget,
  nom,
  onOpenChange,
  onConfirm,
}: {
  budget: Budget
  nom: string
  onOpenChange: (open: boolean) => void
  onConfirm: (budget: Budget) => Promise<void>
}) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  const confirmer = async () => {
    setDeleting(true)
    setError(null)
    try {
      await onConfirm(budget)
      onOpenChange(false)
    } catch (err) {
      // Une dépense imputée entre-temps : le serveur refuse, le dialogue
      // reste ouvert et dit pourquoi.
      if (err instanceof ApiError && err.fields.budget) {
        setError(err.fields.budget.join(" "))
      } else {
        setError(err instanceof Error ? err.message : t("budgets.suppression.impossible"))
      }
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("budgets.suppression.titre", { enveloppe: nom, annee: budget.year })}</DialogTitle>
          <DialogDescription>{t("budgets.suppression.description")}</DialogDescription>
        </DialogHeader>
        <FormError>{error}</FormError>
        <DialogFooter>
          <div>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("commun.annuler")}
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={deleting}
              className="ml-2"
              onClick={() => void confirmer()}
            >
              {deleting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" aria-hidden />
              )}
              {t("budgets.suppression.confirmer")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
