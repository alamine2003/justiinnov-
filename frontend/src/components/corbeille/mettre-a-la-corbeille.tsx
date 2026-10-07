import { useState, type FormEvent } from "react"
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
import { ChampMotif } from "@/components/projects/rename-project"
import { ApiError } from "@/lib/api"
import { mettreALaCorbeille } from "@/lib/corbeille"
import type { NatureSupprimee, ResultatCorbeille } from "@/lib/types"
import { cn } from "@/lib/utils"

/**
 * « Mettre à la corbeille » (décision 120) : le super administrateur retire
 * un projet, un dossier, une ligne ou un justificatif, avec ce qui en
 * dépend, motif à l'appui. Ce composant ne décide pas s'il s'affiche :
 * l'écran qui l'emploie lit `allowed_actions` (`trash`), `can_trash`, ou,
 * pour un projet, la capacité et l'interrupteur de `/api/me/`.
 */
export function MettreALaCorbeille({
  nature,
  id,
  libelle,
  icone = false,
  className,
  onDone,
}: {
  nature: NatureSupprimee
  id: number
  /** Ce que l'écran montre de l'objet : titre, référence ou nom de fichier. */
  libelle: string
  /** Un bouton icône, dans une ligne ou une carte ; un bouton libellé sinon. */
  icone?: boolean
  /** Pour s'aligner sur les boutons voisins (taille d'une liste serrée). */
  className?: string
  onDone: (resultat: ResultatCorbeille) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <>
      {icone ? (
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("corbeille.aria", { libelle })}
          title={t("corbeille.bouton")}
          className={cn("text-destructive hover:text-destructive", className)}
          onClick={() => setOpen(true)}
        >
          <Trash2 className="h-4 w-4" aria-hidden />
        </Button>
      ) : (
        <Button
          variant="outline"
          className="text-destructive hover:text-destructive"
          onClick={() => setOpen(true)}
        >
          <Trash2 className="mr-2 h-4 w-4" aria-hidden />
          {t("corbeille.bouton")}
        </Button>
      )}
      {open && (
        <DialogueDeCorbeille
          nature={nature}
          id={id}
          libelle={libelle}
          onOpenChange={setOpen}
          onDone={onDone}
        />
      )}
    </>
  )
}

/** Monté ouvert seulement : le motif repart vide à chaque ouverture. */
function DialogueDeCorbeille({
  nature,
  id,
  libelle,
  onOpenChange,
  onDone,
}: {
  nature: NatureSupprimee
  id: number
  libelle: string
  onOpenChange: (open: boolean) => void
  onDone: (resultat: ResultatCorbeille) => void
}) {
  const { t } = useTranslation()
  const [motif, setMotif] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!motif.trim()) {
      setError(t("projets.motif.requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      const resultat = await mettreALaCorbeille(nature, id, motif.trim())
      onOpenChange(false)
      onDone(resultat)
    } catch (err) {
      // Le dialogue reste ouvert : le motif saisi n'est pas perdu, et le
      // refus du serveur (corbeille fermée, ligne constatée…) se lit ici.
      if (err instanceof ApiError && Object.keys(err.fields).length > 0) {
        setError(Object.values(err.fields).flat().join(" "))
      } else {
        setError(err instanceof Error ? err.message : t("corbeille.impossible"))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("corbeille.titre", { libelle })}</DialogTitle>
          <DialogDescription>{t(`corbeille.emporte.${nature}`)}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <p className="text-sm text-muted-foreground">{t("corbeille.avertissement")}</p>
          <FormError>{error}</FormError>
          <ChampMotif
            id={`corbeille-motif-${nature}-${id}`}
            value={motif}
            onChange={setMotif}
            placeholder={t("corbeille.motif_placeholder")}
          />
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" variant="destructive" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("corbeille.bouton")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
