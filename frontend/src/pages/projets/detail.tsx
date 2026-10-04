import { useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { AlertTriangle, Archive, Info, Loader2, Upload } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { FilterChips } from "@/components/ui/filter-chips"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { PageHeader } from "@/components/ui/page-header"
import { RefreshIndicator } from "@/components/ui/refresh-indicator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { DossiersTable } from "@/components/expenses/dossiers-table"
import { CompleterProject } from "@/components/projects/completer-project"
import { EditProject } from "@/components/projects/edit-project"
import { ProjectHistory } from "@/components/projects/project-history"
import { RenameProject } from "@/components/projects/rename-project"
import { ProjectKindBadge, ProjectStatusBadge } from "@/components/expenses/status-badge"
import { useAuth } from "@/context/use-auth"
import { fetchDossierKinds, fetchProject } from "@/lib/countries"
import { fetchDossiers } from "@/lib/expenses"
import { REFERENTIEL_PAGE_SIZE, invalidateReferentiel, useReferentiel } from "@/lib/referentiel"
import type { Project } from "@/lib/types"
import { useQuery } from "@/lib/use-query"

/**
 * Fiche d'un projet : ses dossiers prédéfinis, par type, et son historique.
 *
 * Un projet naît avec ses dossiers, un par type de dossier de son type
 * (décision 106) : on ne crée ni ne retire de dossier, on les remplit. Le
 * pays corrige le titre du projet (« Renommer »), le siège le modifie et le
 * complète des dossiers qui lui manquent — chaque fois motif à l'appui
 * (décisions 108 et 109). L'onglet « Historique » (`audit.read`) relit tout
 * ce qui lui est arrivé (décision 110). Le projet « Historique » range les
 * dossiers d'avant la 2.0 ; un projet d'avant la 2.0 attend que le siège le
 * type.
 */
export function ProjetDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const projetId = Number(id)
  const { can } = useAuth()
  const [params, setParams] = useSearchParams()
  const [page, setPage] = useState(1)
  const avecHistorique = can("audit.read")
  const onglet = params.get("onglet") === "historique" && avecHistorique ? "historique" : "dossiers"

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

  // Un projet modifié, renommé ou complété : la fiche, la liste des
  // dossiers et les listes en cache se relisent.
  const projetChange = (modifie: Project) => {
    query.setData(modifie)
    invalidateReferentiel((key) => key === "projects" || key.startsWith("country:"))
    dossiers.reload()
  }

  const changeOnglet = (value: string) => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value === "historique") next.set("onglet", value)
        else next.delete("onglet")
        return next
      },
      { replace: true },
    )
  }

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
    <div className="ecran-plein space-y-6 court:space-y-3">
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
        <RenameProject project={projet} onRenamed={projetChange} />
        <EditProject project={projet} onSaved={projetChange} />
        <CompleterProject project={projet} onDone={projetChange} />
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

      <Tabs className="remplit" value={onglet} onValueChange={(value) => changeOnglet(String(value))}>
        <TabsList
          variant="line"
          aria-label={t("projets.fiche.onglets")}
          className="w-full flex-wrap justify-start border-b border-border/60 group-data-horizontal/tabs:h-auto"
        >
          <TabsTrigger value="dossiers" className="flex-none px-3 py-1.5">
            {t("projets.liste.colonnes.dossiers")}
          </TabsTrigger>
          {avecHistorique && (
            <TabsTrigger value="historique" className="flex-none px-3 py-1.5">
              {t("projets.historique_onglet.titre")}
            </TabsTrigger>
          )}
        </TabsList>
        <TabsContent value="dossiers" className="remplit mt-4 space-y-6 court:mt-2 court:space-y-3">
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

          <Card className="remplit border-border/60 shadow-sm">
            <CardContent className="remplit">
              <DossiersTable
                className="defile"
                dossiers={dossiers.data?.results ?? []}
                loading={dossiers.loading}
                colonne="type"
                vide={
                  typeFilter !== ""
                    ? t("dossiers.liste.vide.aide_filtres")
                    : t("projets.fiche.vide_lecture")
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
        </TabsContent>
        {avecHistorique && (
          <TabsContent value="historique" className="remplit mt-4 court:mt-2">
            {/* L'historique s'allonge sans fin : il défile sous les onglets. */}
            <div className="defile -mx-1 px-1 pb-1">
              <ProjectHistory projectId={projet.id} />
            </div>
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}
