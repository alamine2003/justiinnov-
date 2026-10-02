import { useState, type FormEvent } from "react"
import { Loader2 } from "lucide-react"
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
import { useAuth } from "@/context/use-auth"
import { fetchCountry, fetchDossierKinds } from "@/lib/countries"
import { createDossier } from "@/lib/expenses"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import { scopedTeams, teamRequired } from "@/lib/teams"
import type { Dossier, Project } from "@/lib/types"
import { todayIso } from "@/lib/utils"

/**
 * Ouvre un dossier dans un projet (décision 102).
 *
 * Le pays est celui du projet ; le numéro, `<référence du projet>-D001`,
 * est calculé par le serveur et ne se saisit pas. On choisit le type parmi
 * ceux du type de projet — la liste commune, tenue par le siège — et le
 * titre en reprend le nom tant qu'on ne l'a pas changé : il se renommera à
 * tout moment ensuite.
 */
export function DossierForm({
  project,
  onOpenChange,
  onSaved,
}: {
  project: Project
  onOpenChange: (open: boolean) => void
  onSaved: (dossier: Dossier) => void
}) {
  const { t } = useTranslation()
  const { me } = useAuth()
  const [kind, setKind] = useState<number | "">("")
  const [label, setLabel] = useState("")
  // Le titre suit le type tant que l'utilisateur ne l'a pas écrit lui-même.
  const [labelSaisi, setLabelSaisi] = useState(false)
  const [team, setTeam] = useState<number | "">("")
  const [owner, setOwner] = useState<number | "">("")
  const [date, setDate] = useState(todayIso())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const kinds = useReferentiel(`dossier-kinds:${project.kind}`, () =>
    fetchDossierKinds({ project_kind: project.kind, is_active: true, page_size: REFERENTIEL_PAGE_SIZE }),
  )
  // Équipes et managers du pays du projet, depuis sa fiche : la seule liste
  // qui sache quel manager est rattaché à quel pays.
  const detail = useReferentiel(`country:${project.country}`, () => fetchCountry(project.country))
  // Un manager rattaché à des équipes n'ouvre un dossier que pour elles.
  const teams = scopedTeams((detail.data?.teams ?? []).filter((equipe) => equipe.is_active), me)
  const managers = (detail.data?.managers ?? []).filter((m) => m.is_active)
  const types = kinds.data?.results ?? []

  const choisirType = (valeur: string) => {
    const choisi = valeur === "" ? "" : Number(valeur)
    setKind(choisi)
    if (!labelSaisi) setLabel(types.find((k) => k.id === choisi)?.name ?? "")
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (kind === "") {
      setError(t("projets.dossier.type_requis"))
      return
    }
    if (teamRequired(me) && team === "") {
      setError(t("dossiers.formulaire.equipe_requise"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      const dossier = await createDossier({
        project: project.id,
        kind,
        label: label.trim(),
        team: team === "" ? null : team,
        owner: owner === "" ? null : owner,
        date,
      })
      onSaved(dossier)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : t("dossiers.formulaire.creation_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("projets.dossier.titre", { projet: project.reference ?? project.name })}</DialogTitle>
          <DialogDescription>{t("projets.dossier.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="dos-kind">{t("projets.type_de_dossier")}</Label>
              <NativeSelect
                id="dos-kind"
                value={kind}
                onChange={(e) => choisirType(e.target.value)}
                disabled={kinds.loading}
                required
              >
                <option value="">
                  {types.length === 0 && !kinds.loading
                    ? t("projets.dossier.aucun_type")
                    : t("projets.dossier.choisir_type")}
                </option>
                {types.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dos-date">{t("commun.date")}</Label>
              <Input
                id="dos-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="dos-label">{t("champs.label")}</Label>
            <Input
              id="dos-label"
              value={label}
              onChange={(e) => {
                setLabel(e.target.value)
                setLabelSaisi(true)
              }}
              placeholder={t("projets.dossier.titre_placeholder")}
            />
            <p className="text-xs text-muted-foreground">{t("projets.dossier.titre_aide")}</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="dos-team">{t("champs.team")}</Label>
              <NativeSelect
                id="dos-team"
                value={team}
                onChange={(e) => setTeam(e.target.value === "" ? "" : Number(e.target.value))}
                disabled={detail.loading}
                required={teamRequired(me)}
              >
                <option value="">{t("commun.aucun")}</option>
                {teams.map((equipe) => (
                  <option key={equipe.id} value={equipe.id}>
                    {equipe.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dos-owner">{t("dossiers.formulaire.manager_responsable")}</Label>
              <NativeSelect
                id="dos-owner"
                value={owner}
                onChange={(e) => setOwner(e.target.value === "" ? "" : Number(e.target.value))}
                disabled={detail.loading}
              >
                <option value="">{t("commun.aucun")}</option>
                {managers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>
          {(detail.error || kinds.error) && <FormError>{detail.error ?? kinds.error}</FormError>}
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("commun.creer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
