import { useState, type FormEvent, type ReactNode } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { AlertTriangle, Briefcase, Loader2, Plus, Search } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { FilterChips } from "@/components/ui/filter-chips"
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { PageHeader } from "@/components/ui/page-header"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import { Textarea } from "@/components/ui/textarea"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { CountryTabs } from "@/components/countries/country-tabs"
import { ProjectKindBadge, ProjectStatusBadge } from "@/components/expenses/status-badge"
import { useAuth } from "@/context/use-auth"
import {
  createProject,
  fetchCountries,
  fetchCountry,
  fetchDossierKinds,
  fetchProjects,
  fetchProjectsParPays,
} from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, invalidateReferentiel, useReferentiel } from "@/lib/referentiel"
import { scopedTeams, teamRequired } from "@/lib/teams"
import type { CountrySummary, ProjectKind } from "@/lib/types"
import { typesActifs, useTypesDeProjets } from "@/lib/types-de-projets"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"
import { ApiError } from "@/lib/api"

/**
 * Les projets : la rubrique principale depuis la 2.0 (décision 100).
 *
 * Un projet — congrès, voyage, soutien financier — contient des dossiers
 * déjà typés. On choisit un projet, puis on y ouvre ses dossiers. Le pays
 * et le type vivent dans l'URL (`?country=`, `?kind=`), comme sur la liste
 * des dossiers.
 */
export function ProjetsPage() {
  const { t } = useTranslation()
  const { can, me } = useAuth()
  const navigate = useNavigate()
  const canCreate = can("projets.create")
  const [params, setParams] = useSearchParams()

  // La liste des types vient du serveur (décision 119). Tant qu'elle n'est
  // pas là, le `?kind=` d'un lien est cru : il vient d'une puce ou d'une
  // tuile ; un code inconnu, une fois la liste lue, retombe sur « Tous ».
  const typesDeProjets = useTypesDeProjets()
  const kindParam = params.get("kind") ?? ""
  const kindFilter: ProjectKind =
    typesDeProjets.data === null || typesDeProjets.data.some((type) => type.code === kindParam)
      ? kindParam
      : ""
  const countryParam = Number(params.get("country"))
  const countryFilter: number | "" =
    Number.isInteger(countryParam) && countryParam > 0 ? countryParam : ""

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search)
  const [formOpen, setFormOpen] = useState(false)

  const query = useQuery(
    JSON.stringify({ page, search: debouncedSearch, kindFilter, countryFilter }),
    (signal) => {
      const requestParams: Record<string, unknown> = { page, page_size: PAGE_SIZE }
      if (debouncedSearch) requestParams.search = debouncedSearch
      if (kindFilter) requestParams.kind = kindFilter
      if (countryFilter !== "") requestParams.country = countryFilter
      return fetchProjects(requestParams, signal)
    },
    { fallback: t("projets.liste.chargement_impossible") },
  )

  // Les mêmes onglets que les dossiers (décision 99), comptés par le
  // serveur avec les filtres de la liste sauf le pays.
  const choixPaysVisible = Boolean(me?.has_global_scope) || (me?.countries ?? []).length > 1
  const parPays = useQuery(
    JSON.stringify({ search: debouncedSearch, kindFilter }),
    (signal) => {
      const requestParams: Record<string, unknown> = {}
      if (debouncedSearch) requestParams.search = debouncedSearch
      if (kindFilter) requestParams.kind = kindFilter
      return fetchProjectsParPays(requestParams, signal)
    },
    { enabled: choixPaysVisible, fallback: t("projets.liste.chargement_impossible") },
  )
  const countries = useReferentiel("countries", () =>
    fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: canCreate },
  )

  const projets = query.data?.results ?? []
  const count = query.data?.count ?? 0

  // Un changement de filtre ramène à la première page.
  const changeFilter = (name: "kind" | "country", value: string) => {
    setPage(1)
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set(name, value)
        else next.delete(name)
        return next
      },
      { replace: true },
    )
  }

  return (
    <div className="ecran-plein space-y-6 court:space-y-3">
      <PageHeader title={t("projets.liste.titre")} description={t("projets.liste.description")}>
        {canCreate && (
          <Button onClick={() => setFormOpen(true)}>
            <Plus className="mr-2 h-4 w-4" aria-hidden />
            {t("projets.liste.nouveau")}
          </Button>
        )}
      </PageHeader>

      {query.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{query.error}</AlertDescription>
        </Alert>
      )}

      {choixPaysVisible && (
        <CountryTabs
          value={countryFilter}
          onChange={(value) => changeFilter("country", value)}
          data={parPays.data}
          label={t("projets.liste.filtrer_pays")}
        />
      )}

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative w-full lg:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            placeholder={t("projets.liste.recherche_placeholder")}
            aria-label={t("projets.liste.recherche_aria")}
            className="pl-9"
          />
        </div>
        <FilterChips
          label={t("projets.liste.filtrer_type")}
          value={kindFilter}
          onChange={(value) => changeFilter("kind", value)}
          chips={[
            {
              value: "",
              label: t("commun.tous"),
              count: kindFilter === "" && !query.loading ? count : undefined,
            },
            ...(typesDeProjets.data ?? []).map((type) => ({
              value: type.code,
              label: type.libelle,
              count: kindFilter === type.code && !query.loading ? count : undefined,
            })),
          ]}
        />
      </div>

      <Card className="remplit border-border/60 shadow-sm">
        <CardContent className="remplit">
          <div className="defile overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">{t("projets.reference")}</TableHead>
                  <TableHead scope="col">{t("projets.type")}</TableHead>
                  <TableHead scope="col">{t("commun.pays")}</TableHead>
                  <TableHead scope="col" className="text-center">{t("projets.liste.colonnes.dossiers")}</TableHead>
                  <TableHead scope="col">{t("commun.statut")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={5} />
                ) : projets.length === 0 ? (
                  <EmptyRow
                    colSpan={5}
                    icon={Briefcase}
                    title={t("projets.liste.vide.titre")}
                    hint={
                      debouncedSearch || kindFilter || countryFilter !== ""
                        ? t("projets.liste.vide.aide_filtres")
                        : canCreate
                          ? t("projets.liste.vide.aide_creer")
                          : t("projets.liste.vide.aide_lecture")
                    }
                  />
                ) : (
                  projets.map((projet) => (
                    <TableRow key={projet.id}>
                      <TableCell>
                        <Link
                          to={`/projets/${projet.id}`}
                          className="font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {projet.name}
                        </Link>
                        {projet.reference && (
                          <p className="font-mono text-xs text-muted-foreground">{projet.reference}</p>
                        )}
                      </TableCell>
                      <TableCell>
                        <ProjectKindBadge project={projet} />
                      </TableCell>
                      <TableCell className="text-muted-foreground">{projet.country_name}</TableCell>
                      <TableCell className="text-center">{projet.dossier_count}</TableCell>
                      <TableCell>
                        <ProjectStatusBadge status={projet.status} label={projet.status_display} />
                        {!projet.is_active && (
                          <p className="mt-1 text-xs text-muted-foreground">{t("projets.desactive")}</p>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <Pagination
            page={page}
            count={count}
            onChange={setPage}
            noun={[t("projets.nom_one"), t("projets.nom_other")]}
          />
        </CardContent>
      </Card>

      {formOpen && (
        <ProjectForm
          countries={countries.data?.results ?? []}
          truncated={<TruncatedNotice page={countries.data} noun={t("dossiers.noms_pays")} />}
          onOpenChange={setFormOpen}
          onSaved={(id) => {
            invalidateReferentiel((key) => key === "projects" || key.startsWith("country:"))
            navigate(`/projets/${id}`)
          }}
        />
      )}
    </div>
  )
}

/**
 * Ouvre un projet. Sa référence (`TG-P-2026-001`) est attribuée par le
 * serveur ; le type se choisit ici et ne changera plus. Le projet naît avec
 * ses dossiers prédéfinis, un par type de dossier de son type (décision
 * 106) : le formulaire les annonce, lus dans la liste commune du serveur.
 * L'équipe choisie va sur chaque dossier, donc sur chaque ligne.
 */
function ProjectForm({
  countries,
  truncated,
  onOpenChange,
  onSaved,
}: {
  countries: CountrySummary[]
  truncated: ReactNode
  onOpenChange: (open: boolean) => void
  onSaved: (id: number) => void
}) {
  const { t } = useTranslation()
  const { me } = useAuth()
  const [choix, setCountry] = useState<number | "">("")
  // Un compte d'un seul pays n'a rien à choisir — y compris quand la liste
  // arrive après l'ouverture du dialogue.
  const country: number | "" = choix !== "" ? choix : countries.length === 1 ? countries[0].id : ""
  const [name, setName] = useState("")
  const [kind, setKind] = useState<ProjectKind>("")
  // Seuls les types actifs ouvrent un projet (décision 119).
  const types = typesActifs(useTypesDeProjets().data)
  const [description, setDescription] = useState("")
  const [team, setTeam] = useState<number | "">("")
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  // Les équipes du pays, depuis sa fiche ; un manager rattaché à des
  // équipes n'ouvre un projet que pour l'une des siennes.
  const detail = useReferentiel(
    `country:${country}`,
    () => fetchCountry(Number(country)),
    { enabled: country !== "" },
  )
  const teams = scopedTeams((detail.data?.teams ?? []).filter((equipe) => equipe.is_active), me)
  // Les dossiers que le projet recevra : ceux du type, dans la liste commune.
  const kinds = useReferentiel(
    `dossier-kinds:${kind}`,
    () => fetchDossierKinds({ project_kind: kind, is_active: true, page_size: REFERENTIEL_PAGE_SIZE }),
    { enabled: kind !== "" },
  )
  const dossiersPrevus = kind === "" ? [] : (kinds.data?.results ?? []).map((k) => k.name)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (country === "") {
      setError(t("dossiers.formulaire.choisir_pays"))
      return
    }
    if (!name.trim()) {
      setError(t("projets.formulaire.nom_requis"))
      return
    }
    if (kind === "") {
      setError(t("projets.formulaire.type_requis"))
      return
    }
    if (teamRequired(me) && team === "") {
      setError(t("dossiers.formulaire.equipe_requise"))
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const projet = await createProject({
        country, name: name.trim(), kind, description, team: team === "" ? null : team,
      })
      onSaved(projet.id)
      onOpenChange(false)
    } catch (err) {
      const champs = err instanceof ApiError ? err.fields : {}
      const sousLesChamps = Object.fromEntries(
        ["kind", "team", "name"].filter((cle) => champs[cle]?.length).map((cle) => [cle, champs[cle][0]]),
      )
      setFieldErrors(sousLesChamps)
      if (Object.keys(sousLesChamps).length === 0) {
        setError(err instanceof Error ? err.message : t("dossiers.formulaire.creation_impossible"))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("projets.liste.nouveau")}</DialogTitle>
          <DialogDescription>{t("projets.formulaire.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          {truncated}
          <div className="grid gap-2">
            <Label htmlFor="projet-country">{t("commun.pays")}</Label>
            <NativeSelect
              id="projet-country"
              value={country}
              onChange={(e) => {
                setCountry(e.target.value === "" ? "" : Number(e.target.value))
                // Une équipe appartient à un pays : elle ne suit pas le changement.
                setTeam("")
              }}
              required
            >
              <option value="">
                {countries.length === 0
                  ? t("dossiers.formulaire.aucun_pays")
                  : t("dossiers.formulaire.choisir_pays_option")}
              </option>
              {countries.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.country_ref ? `${c.country_ref} — ` : ""}
                  {c.name}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="projet-name">{t("champs.name")}</Label>
            <Input
              id="projet-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("projets.formulaire.nom_placeholder")}
              required
            />
            <ChampEnErreur message={fieldErrors.name} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="projet-kind">{t("projets.type")}</Label>
            <NativeSelect
              id="projet-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              required
            >
              <option value="">{t("projets.formulaire.choisir_type")}</option>
              {types.map((type) => (
                <option key={type.code} value={type.code}>
                  {type.libelle}
                </option>
              ))}
            </NativeSelect>
            <ChampEnErreur message={fieldErrors.kind} />
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {dossiersPrevus.length > 0
                ? t("projets.formulaire.dossiers_prevus", { dossiers: dossiersPrevus.join(", ") })
                : t("projets.formulaire.type_aide")}
            </p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="projet-team">{t("champs.team")}</Label>
            <NativeSelect
              id="projet-team"
              value={team}
              onChange={(e) => setTeam(e.target.value === "" ? "" : Number(e.target.value))}
              disabled={country === "" || detail.loading}
              required={teamRequired(me)}
            >
              <option value="">{t("commun.aucun")}</option>
              {teams.map((equipe) => (
                <option key={equipe.id} value={equipe.id}>
                  {equipe.name}
                </option>
              ))}
            </NativeSelect>
            <ChampEnErreur message={fieldErrors.team} />
            <p className="text-xs text-muted-foreground">{t("projets.formulaire.equipe_aide")}</p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="projet-description">
              {t("commun.description")}
              <span className="ml-1 text-xs text-muted-foreground">{t("pays.lignes.facultatif")}</span>
            </Label>
            <Textarea
              id="projet-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>
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

/** Le refus du serveur sous le champ qu'il vise. */
function ChampEnErreur({ message }: { message?: string }) {
  if (!message) return null
  return <p role="alert" className="text-xs text-destructive">{message}</p>
}
