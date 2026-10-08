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
import { Textarea } from "@/components/ui/textarea"
import { useAuth } from "@/context/use-auth"
import { ApiError } from "@/lib/api"
import { renameProject } from "@/lib/countries"
import type { Project } from "@/lib/types"

/**
 * « Renommer le projet » : le titre — quel congrès, quel voyage — se
 * corrige par le pays, motif à l'appui, et l'ancien titre reste au journal
 * (décisions 108 et 109). Le siège ne le propose pas : il n'a pas
 * `projets.rename`.
 */
export function RenameProject({
  project,
  onRenamed,
}: {
  project: Project
  onRenamed: (project: Project) => void
}) {
  const { t } = useTranslation()
  const { can } = useAuth()
  const [open, setOpen] = useState(false)

  if (!can("projets.rename")) return null

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <PencilLine className="mr-2 h-4 w-4" aria-hidden />
        {t("projets.renommer.bouton")}
      </Button>
      {open && <RenameDialog project={project} onOpenChange={setOpen} onRenamed={onRenamed} />}
    </>
  )
}

/** Monté ouvert seulement : le champ repart du titre actuel à chaque ouverture. */
function RenameDialog({
  project,
  onOpenChange,
  onRenamed,
}: {
  project: Project
  onOpenChange: (open: boolean) => void
  onRenamed: (project: Project) => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(project.name)
  const [motif, setMotif] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError(t("projets.formulaire.nom_requis"))
      return
    }
    if (!motif.trim()) {
      setError(t("projets.motif.requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      onRenamed(await renameProject(project.id, name.trim(), motif.trim()))
      onOpenChange(false)
    } catch (err) {
      // Le dialogue reste ouvert : le titre et le motif saisis ne sont pas perdus.
      if (err instanceof ApiError && (err.fields.name || err.fields.motif)) {
        setError([...(err.fields.name ?? []), ...(err.fields.motif ?? [])].join(" "))
      } else {
        setError(err instanceof Error ? err.message : t("projets.renommer.impossible"))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("projets.renommer.titre", { reference: project.reference })}</DialogTitle>
          <DialogDescription>{t("projets.renommer.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="rename-projet-name">{t("champs.name")}</Label>
            <Input
              id="rename-projet-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={250}
              required
            />
          </div>
          <ChampMotif id="rename-projet-motif" value={motif} onChange={setMotif} />
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("projets.renommer.bouton")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Le motif d'une modification : obligatoire, gardé au journal (décision 109). */
export function ChampMotif({
  id,
  value,
  onChange,
  placeholder,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  /** La question que le motif doit trancher, quand ce n'est pas une modification. */
  placeholder?: string
}) {
  const { t } = useTranslation()
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{t("projets.motif.libelle")}</Label>
      <Textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={2}
        maxLength={1000}
        placeholder={placeholder ?? t("projets.motif.placeholder")}
        required
      />
      <p className="text-xs text-muted-foreground">{t("projets.motif.aide")}</p>
    </div>
  )
}
