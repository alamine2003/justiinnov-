import { useState, type FormEvent } from "react"
import { Loader2, Settings2 } from "lucide-react"
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
import { NativeSelect } from "@/components/ui/native-select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { ChampMotif } from "@/components/projects/rename-project"
import { useAuth } from "@/context/use-auth"
import { ApiError } from "@/lib/api"
import { updateProject } from "@/lib/countries"
import { PROJECT_STATUSES, projectStatusLabel } from "@/lib/labels"
import type { Project, ProjectKind, ProjectStatus } from "@/lib/types"
import { typesActifs, useTypesDeProjets } from "@/lib/types-de-projets"
import { normalizeDecimal } from "@/lib/utils"

/**
 * « Modifier » le projet, côté siège (`projets.update`, décision 108) :
 * statut, description, budget, activité, et le type d'un projet d'avant la
 * 2.0 — qui reçoit alors ses dossiers prédéfinis. Jamais le titre : il se
 * change par « Renommer », côté pays. Motif obligatoire (décision 109).
 */
export function EditProject({
  project,
  onSaved,
}: {
  project: Project
  onSaved: (project: Project) => void
}) {
  const { t } = useTranslation()
  const { can } = useAuth()
  const [open, setOpen] = useState(false)

  if (!can("projets.update")) return null

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Settings2 className="mr-2 h-4 w-4" aria-hidden />
        {t("projets.modifier.bouton")}
      </Button>
      {open && <EditDialog project={project} onOpenChange={setOpen} onSaved={onSaved} />}
    </>
  )
}

function EditDialog({
  project,
  onOpenChange,
  onSaved,
}: {
  project: Project
  onOpenChange: (open: boolean) => void
  onSaved: (project: Project) => void
}) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<ProjectStatus>(project.status)
  const [description, setDescription] = useState(project.description ?? "")
  const [budget, setBudget] = useState(project.budget ?? "")
  const [active, setActive] = useState(project.is_active)
  const [kind, setKind] = useState<ProjectKind>(project.kind || "")
  // Typer un projet d'avant la 2.0 : parmi les types actifs (décision 119).
  const types = typesActifs(useTypesDeProjets().data)
  const [motif, setMotif] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const montant = budget.trim() ? normalizeDecimal(budget.trim()) : null
    if (budget.trim() && montant === null) {
      setError(t("pays.fiche.budget_nombre"))
      return
    }
    if (!motif.trim()) {
      setError(t("projets.motif.requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      const donnees: Record<string, unknown> = {
        status, description, budget: montant, is_active: active, motif: motif.trim(),
      }
      if (project.a_typer && kind !== "") donnees.kind = kind
      onSaved(await updateProject(project.id, donnees))
      onOpenChange(false)
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length > 0) {
        setError(Object.values(err.fields).flat().join(" "))
      } else {
        setError(err instanceof Error ? err.message : t("projets.modifier.impossible"))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("projets.modifier.titre", { reference: project.reference })}</DialogTitle>
          <DialogDescription>{t("projets.modifier.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          {project.a_typer && (
            <div className="grid gap-2">
              <Label htmlFor="edit-projet-kind">{t("projets.type")}</Label>
              <NativeSelect
                id="edit-projet-kind"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
              >
                <option value="">{t("projets.formulaire.choisir_type")}</option>
                {types.map((type) => (
                  <option key={type.code} value={type.code}>
                    {type.libelle}
                  </option>
                ))}
              </NativeSelect>
              <p className="text-xs text-muted-foreground">{t("projets.modifier.typer_aide")}</p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-projet-status">{t("commun.statut")}</Label>
              <NativeSelect
                id="edit-projet-status"
                value={status}
                onChange={(e) => setStatus(e.target.value as ProjectStatus)}
              >
                {PROJECT_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {projectStatusLabel(t, value)}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-projet-budget">{t("pays.fiche.budget")}</Label>
              <Input
                id="edit-projet-budget"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                inputMode="decimal"
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="edit-projet-description">{t("commun.description")}</Label>
            <Textarea
              id="edit-projet-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch id="edit-projet-active" checked={active} onCheckedChange={setActive} />
            <Label htmlFor="edit-projet-active">{t("projets.modifier.actif")}</Label>
          </div>
          <ChampMotif id="edit-projet-motif" value={motif} onChange={setMotif} />
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("commun.enregistrer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
