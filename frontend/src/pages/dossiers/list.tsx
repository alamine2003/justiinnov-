import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { AlertTriangle, Search, Upload } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { FilterChips } from "@/components/ui/filter-chips"
import { Input } from "@/components/ui/input"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { PageHeader } from "@/components/ui/page-header"
import { CountryTabs } from "@/components/countries/country-tabs"
import { DossiersTable } from "@/components/expenses/dossiers-table"
import { ExportMenu } from "@/components/reporting/export-menu"
import { useAuth } from "@/context/use-auth"
import { fetchDossiers, fetchDossiersParPays } from "@/lib/expenses"
import { WORKFLOW_STATUSES, workflowLabel } from "@/lib/labels"
import type { WorkflowStatus } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"

/**
 * Tous les dossiers visibles, quel que soit leur projet.
 *
 * Depuis la 2.0 (décision 102), la rubrique principale est « Projets » : un
 * dossier s'ouvre dans son projet. Cette liste reste pour les tuiles du
 * pilotage (`?status=`), la recherche transverse et l'export ; elle quitte
 * la navigation.
 */
export function DossiersPage() {
  const { t } = useTranslation()
  const { can, me } = useAuth()
  const canCreate = can("expenses.create")
  const [params, setParams] = useSearchParams()

  // Le statut et le pays vivent dans l'URL : une tuile du tableau de bord
  // ou un favori doivent rouvrir la même vue.
  const statusParam = params.get("status") ?? ""
  const statusFilter = (WORKFLOW_STATUSES as string[]).includes(statusParam)
    ? (statusParam as WorkflowStatus)
    : ""
  const countryParam = Number(params.get("country"))
  const countryFilter: number | "" =
    Number.isInteger(countryParam) && countryParam > 0 ? countryParam : ""

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search)
  const [exportError, setExportError] = useState<string | null>(null)

  const query = useQuery(
    JSON.stringify({ page, search: debouncedSearch, statusFilter, countryFilter }),
    (signal) => {
      const requestParams: Record<string, unknown> = { page, page_size: PAGE_SIZE }
      if (debouncedSearch) requestParams.search = debouncedSearch
      if (statusFilter) requestParams.status = statusFilter
      if (countryFilter !== "") requestParams.country = countryFilter
      return fetchDossiers(requestParams, signal)
    },
    { fallback: t("dossiers.liste.chargement_impossible") },
  )

  const dossiers = query.data?.results ?? []
  const count = query.data?.count ?? 0

  // Un dossier appartient à un pays (décision 89) : dès que le compte en
  // voit plusieurs — le siège, ou un manager rattaché à plusieurs pays —,
  // la liste se sépare en onglets, un par pays, chacun avec le nombre de
  // dossiers qu'il affichera. Les pays et leurs comptes viennent du serveur
  // (`/dossiers/par-pays/`), avec les mêmes filtres que la liste sauf le
  // pays ; le serveur cloisonne de toute façon.
  const choixPaysVisible = Boolean(me?.has_global_scope) || (me?.countries ?? []).length > 1
  const parPays = useQuery(
    JSON.stringify({ search: debouncedSearch, statusFilter }),
    (signal) => {
      const requestParams: Record<string, unknown> = {}
      if (debouncedSearch) requestParams.search = debouncedSearch
      if (statusFilter) requestParams.status = statusFilter
      return fetchDossiersParPays(requestParams, signal)
    },
    { enabled: choixPaysVisible, fallback: t("dossiers.liste.chargement_impossible") },
  )

  // Un changement de filtre ramène à la première page : rester en page 4
  // d'un résultat qui n'en compte plus qu'une afficherait un tableau vide.
  const changeFilter = (name: "status" | "country", value: string) => {
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
  const changeStatus = (value: string) => changeFilter("status", value)

  return (
    <div className="ecran-plein space-y-6 court:space-y-3">
      <PageHeader
        title={t("dossiers.liste.titre")}
        description={t("dossiers.liste.description")}
      >
        <ExportMenu country={countryFilter} onError={setExportError} />
        {can("data.import") && (
          <Button variant="outline" nativeButton={false} render={<Link to="/dossiers/import" />}>
            <Upload className="mr-2 h-4 w-4" aria-hidden />
            {t("dossiers.import.bouton")}
          </Button>
        )}
      </PageHeader>

      {(query.error || exportError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{exportError ?? query.error}</AlertDescription>
        </Alert>
      )}

      {choixPaysVisible && (
        <CountryTabs
          value={countryFilter}
          onChange={(value) => changeFilter("country", value)}
          data={parPays.data}
          label={t("dossiers.liste.filtrer_pays")}
        />
      )}

      {/* Six statuts tiennent en pastilles : les voir tous vaut mieux que les
          dérouler, et le compte du serveur se pose sur celui qui est actif. */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative w-full lg:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            placeholder={t("dossiers.liste.recherche_placeholder")}
            aria-label={t("dossiers.liste.recherche_aria")}
            className="pl-9"
          />
        </div>
        <FilterChips
          label={t("dossiers.liste.filtrer_statut")}
          value={statusFilter}
          onChange={changeStatus}
          chips={[
            {
              value: "",
              label: t("commun.tous"),
              count: statusFilter === "" && !query.loading ? count : undefined,
            },
            ...WORKFLOW_STATUSES.map((value) => ({
              value,
              label: workflowLabel(t, value),
              count: statusFilter === value && !query.loading ? count : undefined,
            })),
          ]}
        />
      </div>

      <Card className="remplit border-border/60 shadow-sm">
        <CardContent className="remplit">
          <DossiersTable
            className="defile"
            dossiers={dossiers}
            loading={query.loading}
            colonne="projet"
            vide={
              canCreate ? t("dossiers.liste.vide.aide_creer") : t("dossiers.liste.vide.aide_filtres")
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

    </div>
  )
}
