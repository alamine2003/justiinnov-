import { useState, type FormEvent } from "react"
import { Link } from "react-router-dom"
import { History, Loader2, Pencil, Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
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
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { ChampMotif } from "@/components/projects/rename-project"
import { useAuth } from "@/context/use-auth"
import { ApiError } from "@/lib/api"
import {
  createDossierKind,
  createProjectType,
  fetchDossierKinds,
  fetchProjectTypes,
  updateDossierKind,
  updateProjectType,
} from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, invalidateReferentiel } from "@/lib/referentiel"
import { STATUS_TONES } from "@/lib/status-styles"
import type { DossierKind, ProjectType } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { Erreur } from "@/pages/configuration/section-states"

/**
 * Les types de projets et, sous chacun, ses types de dossiers (décision 119).
 *
 * Deux listes communes aux dix-sept filiales, tenues par le super
 * administrateur seul (`project_types.manage`, `dossier_kinds.manage`) ;
 * l'administrateur les lit. Un type de projet porte ses types de dossiers :
 * tout projet ouvert sous lui reçoit d'office un dossier par type de
 * dossier actif, dans l'ordre affiché (décision 106). On ajoute, renomme,
 * ordonne et désactive ; rien ne se supprime, et toute modification exige
 * un motif, gardé au journal (décision 109).
 *
 * Le regroupement par type est un rangement de l'affichage : les deux
 * listes viennent du serveur, déjà triées.
 */
export function ProjectTypesSection() {
  const { t } = useTranslation()
  const { can } = useAuth()
  const peutTenirLesTypes = can("project_types.manage")
  const peutTenirLesDossiers = can("dossier_kinds.manage")
  const types = useQuery(
    "configuration:types-de-projets",
    (signal) => fetchProjectTypes({ page_size: REFERENTIEL_PAGE_SIZE }, signal),
    { fallback: t("configuration.types_projets.chargement_impossible") },
  )
  const kinds = useQuery(
    "configuration:types-de-dossiers",
    (signal) => fetchDossierKinds({ page_size: REFERENTIEL_PAGE_SIZE }, signal),
    { fallback: t("configuration.types_dossiers.chargement_impossible") },
  )
  const [typeEnCours, setTypeEnCours] = useState<ProjectType | "nouveau" | null>(null)
  const [kindEnCours, setKindEnCours] = useState<
    { type: ProjectType; kind: DossierKind | null } | null
  >(null)

  const apresEcriture = () => {
    // Formulaires de projet, filtres, import : ils gardent ces listes en cache.
    invalidateReferentiel(
      (key) => key.startsWith("project-types:") || key.startsWith("dossier-kinds:"),
    )
    types.reload()
    kinds.reload()
  }

  const listeDesTypes = types.data?.results ?? []
  const listeDesKinds = kinds.data?.results ?? []

  return (
    <div className="space-y-4">
      {types.error && <Erreur message={types.error} />}
      {kinds.error && <Erreur message={kinds.error} />}
      <TruncatedNotice page={types.data} noun={t("configuration.types_projets.noun_pluriel")} />
      <TruncatedNotice page={kinds.data} noun={t("configuration.types_dossiers.noun_pluriel")} />

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl space-y-1">
          <h2 className="text-sm font-semibold">{t("configuration.types_projets.titre")}</h2>
          <p className="text-sm text-muted-foreground">
            {t("configuration.types_projets.description")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {can("audit.read") && (
            <Button
              variant="outline"
              size="sm"
              nativeButton={false}
              render={<Link to="/audit?onglet=referentiel&model_name=project_type" />}
            >
              <History className="h-4 w-4" />
              {t("configuration.types_projets.historique")}
            </Button>
          )}
          {peutTenirLesTypes && (
            <Button size="sm" onClick={() => setTypeEnCours("nouveau")}>
              <Plus className="h-4 w-4" />
              {t("configuration.types_projets.ajouter")}
            </Button>
          )}
        </div>
      </div>

      {types.loading && listeDesTypes.length === 0 ? (
        <Card className="border-border/60 shadow-sm">
          <CardContent>
            <Table>
              <TableBody>
                <SkeletonRows rows={3} columns={4} />
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : listeDesTypes.length === 0 && !types.error ? (
        <Card className="border-border/60 shadow-sm">
          <CardContent className="py-8 text-center">
            <p className="text-sm font-medium">{t("configuration.types_projets.aucun")}</p>
            <p className="text-sm text-muted-foreground">
              {t("configuration.types_projets.aucun_aide")}
            </p>
          </CardContent>
        </Card>
      ) : (
        listeDesTypes.map((type) => (
          <CarteDeType
            key={type.id}
            type={type}
            kinds={listeDesKinds.filter((kind) => kind.project_kind === type.code)}
            chargement={kinds.loading}
            peutModifier={peutTenirLesTypes}
            peutTenirLesDossiers={peutTenirLesDossiers}
            onModifier={() => setTypeEnCours(type)}
            onAjouterUnDossier={() => setKindEnCours({ type, kind: null })}
            onModifierUnDossier={(kind) => setKindEnCours({ type, kind })}
          />
        ))
      )}

      {typeEnCours !== null && (
        <DialogueDeType
          type={typeEnCours === "nouveau" ? null : typeEnCours}
          onClose={() => setTypeEnCours(null)}
          onSaved={apresEcriture}
        />
      )}
      {kindEnCours !== null && (
        <DialogueDeKind
          type={kindEnCours.type}
          kind={kindEnCours.kind}
          onClose={() => setKindEnCours(null)}
          onSaved={apresEcriture}
        />
      )}
    </div>
  )
}

function BadgeDEtat({ actif }: { actif: boolean }) {
  const { t } = useTranslation()
  return actif ? (
    <Badge className={STATUS_TONES.SUCCES}>{t("commun.actif")}</Badge>
  ) : (
    <Badge className={STATUS_TONES.ARCHIVE}>{t("commun.desactive")}</Badge>
  )
}

function CarteDeType({
  type,
  kinds,
  chargement,
  peutModifier,
  peutTenirLesDossiers,
  onModifier,
  onAjouterUnDossier,
  onModifierUnDossier,
}: {
  type: ProjectType
  kinds: DossierKind[]
  chargement: boolean
  peutModifier: boolean
  peutTenirLesDossiers: boolean
  onModifier: () => void
  onAjouterUnDossier: () => void
  onModifierUnDossier: (kind: DossierKind) => void
}) {
  const { t } = useTranslation()
  // Le serveur compte les types de dossiers actifs : un type de projet
  // sans aucun n'ouvre pas de projet (décision 106).
  const sansDossier = type.is_active && type.dossier_kinds_actifs === 0

  return (
    <Card className="border-border/60 shadow-sm">
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">{type.name}</h3>
              {type.name_en && (
                <span className="text-sm text-muted-foreground">· {type.name_en}</span>
              )}
              <BadgeDEtat actif={type.is_active} />
              {sansDossier && (
                <Badge className={STATUS_TONES.ATTENTE}>
                  {t("configuration.types_projets.sans_dossier")}
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              <span className="font-mono">{type.code}</span>
              {" · "}
              {t("configuration.types_projets.ordre", { ordre: type.ordre })}
              {/* Servi au siège seul : il compte les dix-sept filiales. */}
              {type.projets !== null && (
                <>
                  {" · "}
                  {t("configuration.types_projets.projets", { count: type.projets })}
                </>
              )}
            </p>
            {type.description && (
              <p className="text-sm text-muted-foreground">{type.description}</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {peutTenirLesDossiers && (
              <Button variant="outline" size="sm" onClick={onAjouterUnDossier}>
                <Plus className="h-4 w-4" />
                {t("configuration.types_dossiers.ajouter")}
              </Button>
            )}
            {peutModifier && (
              <Button
                variant="outline"
                size="sm"
                onClick={onModifier}
                aria-label={t("configuration.types_projets.modifier_aria", { nom: type.name })}
              >
                <Pencil className="h-4 w-4" />
                {t("configuration.types_projets.modifier")}
              </Button>
            )}
          </div>
        </div>

        <div className="overflow-x-auto rounded-lg border border-border/60">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">{t("configuration.types_dossiers.ordre")}</TableHead>
                <TableHead>{t("configuration.types_dossiers.titre_colonne")}</TableHead>
                <TableHead>{t("commun.description")}</TableHead>
                <TableHead>{t("commun.statut")}</TableHead>
                {peutTenirLesDossiers && (
                  <TableHead className="w-12">
                    <span className="sr-only">{t("commun.actions")}</span>
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {chargement && kinds.length === 0 ? (
                <SkeletonRows rows={2} columns={peutTenirLesDossiers ? 5 : 4} />
              ) : kinds.length === 0 ? (
                <EmptyRow
                  colSpan={peutTenirLesDossiers ? 5 : 4}
                  title={t("configuration.types_dossiers.aucun")}
                />
              ) : (
                kinds.map((kind) => (
                  <TableRow key={kind.id}>
                    <TableCell className="tabular-nums text-muted-foreground">
                      {kind.ordre}
                    </TableCell>
                    <TableCell className="font-medium">{kind.name}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {kind.description || "—"}
                    </TableCell>
                    <TableCell>
                      <BadgeDEtat actif={kind.is_active} />
                    </TableCell>
                    {peutTenirLesDossiers && (
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => onModifierUnDossier(kind)}
                          aria-label={t("configuration.types_dossiers.modifier_aria", {
                            nom: kind.name,
                          })}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function ChampEnErreur({ messages }: { messages?: string[] }) {
  if (!messages?.length) return null
  return <p role="alert" className="text-xs text-destructive">{messages.join(" ")}</p>
}

/** Le formulaire commun aux deux dialogues : enregistrement, erreurs par champ. */
function useEnregistrement(onSaved: () => void, onClose: () => void) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string[]>>({})

  const enregistrer = async (ecrire: () => Promise<unknown>) => {
    setSaving(true)
    setError(null)
    setFields({})
    try {
      await ecrire()
      onSaved()
      onClose()
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length > 0) {
        setFields(err.fields)
        setError(t("configuration.types_projets.erreur_champs"))
      } else {
        setError(err instanceof Error ? err.message : t("erreurs.enregistrement_impossible"))
      }
    } finally {
      setSaving(false)
    }
  }
  return { saving, error, setError, fields, enregistrer }
}

function PiedDeDialogue({ saving, onClose }: { saving: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <DialogFooter>
      <div>
        <Button type="button" variant="outline" onClick={onClose}>
          {t("commun.annuler")}
        </Button>
        <Button type="submit" disabled={saving} className="ml-2">
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t("commun.enregistrer")}
        </Button>
      </div>
    </DialogFooter>
  )
}

function ChampOrdre({
  id,
  value,
  onChange,
  erreurs,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  erreurs?: string[]
}) {
  const { t } = useTranslation()
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{t("configuration.types_dossiers.ordre")}</Label>
      <Input
        id={id}
        type="number"
        min={0}
        inputMode="numeric"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t("configuration.types_projets.ordre_placeholder")}
        aria-describedby={`${id}-aide`}
      />
      <p id={`${id}-aide`} className="text-xs text-muted-foreground">
        {t("configuration.types_projets.ordre_aide")}
      </p>
      <ChampEnErreur messages={erreurs} />
    </div>
  )
}

function DialogueDeType({
  type,
  onClose,
  onSaved,
}: {
  type: ProjectType | null
  onClose: () => void
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(type?.name ?? "")
  const [nameEn, setNameEn] = useState(type?.name_en ?? "")
  const [description, setDescription] = useState(type?.description ?? "")
  // Vide à la création : le serveur range le type après les autres.
  const [ordre, setOrdre] = useState(type ? String(type.ordre) : "")
  const [actif, setActif] = useState(type?.is_active ?? true)
  const [motif, setMotif] = useState("")
  const { saving, error, setError, fields, enregistrer } = useEnregistrement(onSaved, onClose)

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError(t("configuration.types_projets.nom_requis"))
      return
    }
    if (type && !motif.trim()) {
      setError(t("projets.motif.requis"))
      return
    }
    const donnees = {
      name: name.trim(),
      name_en: nameEn.trim(),
      description: description.trim(),
      ...(ordre.trim() !== "" ? { ordre: Number(ordre) } : {}),
      is_active: actif,
      ...(type ? { motif: motif.trim() } : {}),
    }
    void enregistrer(() =>
      type ? updateProjectType(type.id, donnees) : createProjectType(donnees),
    )
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {type
              ? t("configuration.types_projets.dialogue_modifier", { nom: type.libelle })
              : t("configuration.types_projets.dialogue_ajouter")}
          </DialogTitle>
          <DialogDescription>
            {type
              ? t("configuration.types_projets.dialogue_modifier_aide", { code: type.code })
              : t("configuration.types_projets.dialogue_ajouter_aide")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          {/* L'un sous l'autre : côte à côte, « Nom en anglais (facultatif) »
              passait sur deux lignes et décalait son champ. */}
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="type-nom">{t("configuration.types_projets.nom")}</Label>
              <Input
                id="type-nom"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("configuration.types_projets.nom_placeholder")}
                maxLength={80}
                required
              />
              <ChampEnErreur messages={fields.name} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="type-nom-en">
                {t("configuration.types_projets.nom_en")}
                <span className="ml-1 text-xs text-muted-foreground">
                  {t("pays.lignes.facultatif")}
                </span>
              </Label>
              <Input
                id="type-nom-en"
                value={nameEn}
                onChange={(e) => setNameEn(e.target.value)}
                placeholder={t("configuration.types_projets.nom_en_placeholder")}
                maxLength={80}
              />
              <ChampEnErreur messages={fields.name_en} />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="type-description">
              {t("commun.description")}
              <span className="ml-1 text-xs text-muted-foreground">
                {t("pays.lignes.facultatif")}
              </span>
            </Label>
            <Textarea
              id="type-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          <ChampOrdre id="type-ordre" value={ordre} onChange={setOrdre} erreurs={fields.ordre} />
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-1">
              <Label htmlFor="type-actif" className="text-sm">{t("commun.actif")}</Label>
              <p className="text-xs text-muted-foreground">
                {t("configuration.types_projets.actif_aide")}
              </p>
            </div>
            <Switch id="type-actif" checked={actif} onCheckedChange={setActif} />
          </div>
          {type && (
            <>
              <ChampMotif id="type-motif" value={motif} onChange={setMotif} />
              <ChampEnErreur messages={fields.motif} />
            </>
          )}
          <PiedDeDialogue saving={saving} onClose={onClose} />
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DialogueDeKind({
  type,
  kind,
  onClose,
  onSaved,
}: {
  type: ProjectType
  kind: DossierKind | null
  onClose: () => void
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(kind?.name ?? "")
  const [description, setDescription] = useState(kind?.description ?? "")
  // Vide à la création : le serveur range le type après ceux de son type de projet.
  const [ordre, setOrdre] = useState(kind ? String(kind.ordre) : "")
  const [actif, setActif] = useState(kind?.is_active ?? true)
  const [motif, setMotif] = useState("")
  const { saving, error, setError, fields, enregistrer } = useEnregistrement(onSaved, onClose)

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError(t("configuration.types_dossiers.nom_requis"))
      return
    }
    if (kind && !motif.trim()) {
      setError(t("projets.motif.requis"))
      return
    }
    const donnees = {
      name: name.trim(),
      description: description.trim(),
      ...(ordre.trim() !== "" ? { ordre: Number(ordre) } : {}),
      is_active: actif,
      ...(kind ? { motif: motif.trim() } : { project_kind: type.code }),
    }
    void enregistrer(() =>
      kind ? updateDossierKind(kind.id, donnees) : createDossierKind(donnees),
    )
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {kind
              ? t("configuration.types_dossiers.dialogue_modifier", { nom: kind.name })
              : t("configuration.types_dossiers.dialogue_ajouter", { type: type.libelle })}
          </DialogTitle>
          <DialogDescription>{t("configuration.types_dossiers.dialogue_aide")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="kind-nom">{t("configuration.types_dossiers.titre_colonne")}</Label>
            <Input
              id="kind-nom"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("configuration.types_dossiers.nom_placeholder")}
              maxLength={120}
              required
            />
            <ChampEnErreur messages={fields.name ?? fields.non_field_errors} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="kind-description">
              {t("commun.description")}
              <span className="ml-1 text-xs text-muted-foreground">
                {t("pays.lignes.facultatif")}
              </span>
            </Label>
            <Textarea
              id="kind-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          <ChampOrdre id="kind-ordre" value={ordre} onChange={setOrdre} erreurs={fields.ordre} />
          <div className="flex items-center justify-between rounded-lg border p-3">
            <Label htmlFor="kind-actif" className="text-sm">{t("commun.actif")}</Label>
            <Switch id="kind-actif" checked={actif} onCheckedChange={setActif} />
          </div>
          {kind && (
            <>
              <ChampMotif id="kind-motif" value={motif} onChange={setMotif} />
              <ChampEnErreur messages={fields.motif} />
            </>
          )}
          <PiedDeDialogue saving={saving} onClose={onClose} />
        </form>
      </DialogContent>
    </Dialog>
  )
}
