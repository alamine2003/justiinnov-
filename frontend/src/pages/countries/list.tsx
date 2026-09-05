import { useState } from "react"
import { AlertTriangle } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { CountryForm, type CountryFormValues } from "@/components/countries/country-form"
import { CountryTable } from "@/components/countries/country-table"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { PageHeader } from "@/components/ui/page-header"
import {
  createCountry,
  fetchCountries,
  updateCountry,
} from "@/lib/countries"
import { useAuth } from "@/context/use-auth"
import { invalidateReferentiel } from "@/lib/referentiel"
import type { CountrySummary } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"

type StatusFilter = "all" | "active" | "inactive"

export function CountriesPage() {
  const { t } = useTranslation()
  const { can } = useAuth()
  const canManage = can("countries.create") && can("countries.update")
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<CountrySummary | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)

  const query = useQuery(
    JSON.stringify({ page, debouncedSearch, statusFilter }),
    (signal) => {
      const params: Record<string, unknown> = { page, page_size: PAGE_SIZE }
      if (statusFilter !== "all") params.is_active = statusFilter === "active"
      if (debouncedSearch) params.search = debouncedSearch
      return fetchCountries(params, signal)
    },
    { fallback: t("pays.liste.chargement_impossible") },
  )

  const afterWrite = () => {
    // Les listes déroulantes des autres pages gardent une copie en cache.
    invalidateReferentiel("countries")
    query.reload()
  }

  const handleSave = async (values: CountryFormValues) => {
    if (editing) {
      await updateCountry(editing.id, values)
      // La fiche du pays (devise, fuseau, équipes) est en cache pour la saisie.
      invalidateReferentiel(`country:${editing.id}`)
    } else {
      await createCountry(values)
    }
    setEditing(null)
    afterWrite()
  }

  const handleToggle = async (country: CountrySummary) => {
    setTogglingId(country.id)
    setActionError(null)
    try {
      await updateCountry(country.id, { is_active: !country.is_active })
      invalidateReferentiel(`country:${country.id}`)
      afterWrite()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t("pays.liste.statut_impossible"))
    } finally {
      setTogglingId(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("pays.liste.titre")} description={t("pays.liste.description")} />

      {(query.error || actionError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{actionError ?? query.error}</AlertDescription>
        </Alert>
      )}

      <CountryTable
        countries={query.data?.results ?? []}
        loading={query.loading}
        search={search}
        onSearchChange={(value) => {
          setSearch(value)
          setPage(1)
        }}
        onFilterStatus={(status) => {
          setStatusFilter(status)
          setPage(1)
        }}
        statusFilter={statusFilter}
        onAdd={() => {
          setEditing(null)
          setFormOpen(true)
        }}
        onEdit={(country) => {
          setEditing(country)
          setFormOpen(true)
        }}
        onToggle={(country) => void handleToggle(country)}
        togglingId={togglingId}
        canManage={canManage}
      />

      <Pagination
        page={page}
        count={query.data?.count ?? 0}
        onChange={setPage}
        noun={[t("pays.liste.nom_singulier"), t("pays.liste.nom_pluriel")]}
      />

      <CountryForm
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open)
          if (!open) setEditing(null)
        }}
        onSave={handleSave}
        initial={
          editing
            ? {
                name: editing.name,
                code: editing.code,
                currency: editing.currency,
                currency_symbol: editing.currency_symbol,
                timezone: editing.timezone,
                is_active: editing.is_active,
              }
            : undefined
        }
        title={
          editing
            ? t("pays.liste.modifier_titre", { nom: editing.name })
            : t("pays.formulaire.titre_ajout")
        }
      />
    </div>
  )
}
