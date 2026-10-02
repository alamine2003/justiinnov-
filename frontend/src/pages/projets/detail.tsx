import { useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import { AlertTriangle, Archive, Info, Loader2, Plus, Upload } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { FilterChips } from "@/components/ui/filter-chips"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { PageHeader } from "@/components/ui/page-header"
import { RefreshIndicator } from "@/components/ui/refresh-indicator"
import { DossierForm } from "@/components/expenses/dossier-form"
import { DossiersTable } from "@/components/expenses/dossiers-table"
import { ProjectKindBadge, ProjectStatusBadge } from "@/components/expenses/status-badge"
import { useAuth } from "@/context/use-auth"
import { fetchDossierKinds, fetchProject } from "@/lib/countries"
import { fetchDossiers } from "@/lib/expenses"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import { useQuery } from "@/lib/use-query"

/**
 * Fiche d'un projet : ses dossiers, par type, et l'ouverture d'un nouveau.
 *
 * Un dossier s'ouvre dans un projet actif et typé (décision 102) : le
 * serveur le dit (`accepte_des_dossiers`), et « Nouveau dossier » n'est
 * proposé qu'alors. Le projet « Historique » range les dossiers d'avant la
 * 2.0 ; un projet d'avant la 2.0 attend que le siège le type.
 */
export function ProjetDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const projetId = Number(id)
  const { can } = useAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [page, setPage] = useState(1)
  const [formOpen, setFormOpen] = useState(false)

  const typeParam = Number(params.get("type"))
  const typeFilter: number | "" = Number.isInteger(typeParam) && typeParam > 0 ? typeParam : ""

  // Le projet est celui de l'URL : rien du précédent ne reste affiché
  // sous la nouvelle adresse (`keepPreviousData: false`).
  const query = useQuery(
    `projet:${projetId}`,
    (signal) => fetchProject(projetId, signal),
    { fallback: t("projets.fiche.chargement_impossible"), keepPreviousData: false },
  )
  const projet = query.data

  const dossiers = useQuery(
    JSON.stringify({ projetId, page, typeFilter }),
    (signal) => {
      const requestParams: Record<string, unknown> = { project: projetId, page, page_size: PAGE_SIZE }
      if (typeFilter !== "") requestParams.kind = typeFilter
      return fetchDossiers(requestParams, signal)
    },
    { fallback: t("dossiers.liste.chargement_impossible") },
  )

  // Les types de ce type de projet, désactivés compris : un dossier ouvert
  // sous un type retiré depuis doit rester filtrable.
  const kinds = useReferentiel(
    `dossier-kinds:tous:${projet?.kind}`,
    () => fetchDossierKinds({ project_kind: projet?.kind, page_size: REFERENTIEL_PAGE_SIZE }),
    { enabled: Boolean(projet?.kind) },
  )

  const changeType = (value: string) => {
    setPage(1)
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set("type", value)
        else next.delete("type")
        return next
      },
      { replace: true },
    )
  }

  if (query.loading && !projet) {
    return (
      <div className="flex h-64 items-center justify-center" aria-busy="true">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="sr-only">{t("projets.fiche.chargement")}</span>
      </div>
    )
  }

  if (!projet) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>{t("projets.fiche.introuvable_titre")}</AlertTitle>
        <AlertDescription>{query.error ?? t("projets.fiche.introuvable_texte")}</AlertDescription>
      </Alert>
    )
  }

  const ouvert = projet.accepte_des_dossiers
  const count = dossiers.data?.count ?? 0

  return (
    <div className="space-y-6">
      {dossiers.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{dossiers.error}</AlertDescription>
        </Alert>
      )}

      <PageHeader
        title={projet.name}
        description={
          <>
            <span className="mr-2 inline-flex gap-1.5 align-middle">
              <ProjectKindBadge project={projet} />
              <ProjectStatusBadge status={projet.status} label={projet.status_display} />
            </span>
            {projet.reference && <span className="font-mono">{projet.reference}</span>}
            {projet.reference && " · "}
            {projet.country_name}
            {query.refreshing && (
              <RefreshIndicator className="ml-2" label={t("projets.fiche.actualisation")} />
            )}
            {projet.description && <span className="mt-1 block">{projet.description}</span>}
          </>
        }
      >
        {ouvert && can("data.import") && (
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link to={`/dossiers/import?project=${projet.id}`} />}
          >
            <Upload className="mr-2 h-4 w-4" aria-hidden />
            {t("dossiers.import.bouton")}
          </Button>
        )}
        {ouvert && can("expenses.create") && (
          <Button onClick={() => setFormOpen(true)}>
            <Plus className="mr-2 h-4 w-4" aria-hidden />
            {t("dossiers.liste.nouveau")}
          </Button>
        )}
      </PageHeader>

      {/* Pourquoi on ne peut pas y ouvrir de dossier : le dire plutôt que
          de laisser chercher un bouton absent. */}
      {projet.is_historical ? (
        <Alert>
          <Archive className="h-4 w-4" />
          <AlertTitle>{t("projets.historique")}</AlertTitle>
          <AlertDescription>{t("projets.fiche.historique_aide")}</AlertDescription>
        </Alert>
      ) : projet.a_typer ? (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>{t("projets.a_typer")}</AlertTitle>
          <AlertDescription>{t("projets.fiche.a_typer_aide")}</AlertDescription>
        </Alert>
      ) : (
        !projet.is_active && (
          <Alert>
            <Info className="h-4 w-4" />
            <AlertTitle>{t("projets.desactive")}</AlertTitle>
            <AlertDescription>{t("projets.fiche.desactive_aide")}</AlertDescription>
          </Alert>
        )
      )}

      {(kinds.data?.results ?? []).length > 0 && (
        <FilterChips
          label={t("projets.fiche.filtrer_type")}
          value={typeFilter === "" ? "" : String(typeFilter)}
          onChange={changeType}
          chips={[
            {
              value: "",
              label: t("commun.tous"),
              count: typeFilter === "" && !dossiers.loading ? count : undefined,
            },
            ...(kinds.data?.results ?? []).map((k) => ({
              value: String(k.id),
              label: k.name,
              count: typeFilter === k.id && !dossiers.loading ? count : undefined,
            })),
          ]}
        />
      )}

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <DossiersTable
            dossiers={dossiers.data?.results ?? []}
            loading={dossiers.loading}
            colonne="type"
            vide={
              ouvert && can("expenses.create")
                ? t("projets.fiche.vide_creer")
                : t("dossiers.liste.vide.aide_filtres")
            }
          />
          <Pagination
            page={page}
            count={count}
            onChange={setPage}
            noun={[t("dossiers.nom_one"), t("dossiers.nom_other")]}
          />
        </CardContent>
      </Card>

      {formOpen && (
        <DossierForm
          project={projet}
          onOpenChange={setFormOpen}
          onSaved={(dossier) => navigate(`/dossiers/${dossier.id}`)}
        />
      )}
    </div>
  )
}
