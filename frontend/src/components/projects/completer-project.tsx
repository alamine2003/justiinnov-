import { useState } from "react"
import { FolderPlus, Loader2 } from "lucide-react"
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
import { useAuth } from "@/context/use-auth"
import { completerProject } from "@/lib/countries"
import type { Project } from "@/lib/types"

/**
 * « Compléter les dossiers », côté siège (décision 106) : ouvre les
 * dossiers prédéfinis qui manquent au projet — un projet réactivé, un type
 * de dossier ajouté depuis. Jamais d'office ; sans auteur, ils reviennent
 * au pays. Proposé seulement si le projet accepte des dossiers.
 */
export function CompleterProject({
  project,
  onDone,
}: {
  project: Project
  onDone: (project: Project) => void
}) {
  const { t } = useTranslation()
  const { can } = useAuth()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  if (!can("projets.update") || !project.accepte_des_dossiers) return null

  const confirmer = async () => {
    setSaving(true)
    setError(null)
    try {
      onDone(await completerProject(project.id))
      setOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : t("projets.completer.impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <FolderPlus className="mr-2 h-4 w-4" aria-hidden />
        {t("projets.completer.bouton")}
      </Button>
      {open && (
        <Dialog open onOpenChange={setOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("projets.completer.titre", { reference: project.reference })}</DialogTitle>
              <DialogDescription>{t("projets.completer.description")}</DialogDescription>
            </DialogHeader>
            <FormError>{error}</FormError>
            <DialogFooter>
              <div>
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                  {t("commun.annuler")}
                </Button>
                <Button type="button" disabled={saving} className="ml-2" onClick={confirmer}>
                  {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t("projets.completer.confirmer")}
                </Button>
              </div>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  )
}
