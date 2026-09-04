import { useState } from "react"
import { AlertTriangle } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { CountryForm, type CountryFormValues } from "@/components/countries/country-form"
import { CountryTable } from "@/components/countries/country-table"
import { createCountry, fetchCountries, updateCountry } from "@/lib/countries"
import { invalidateReferentiel } from "@/lib/referentiel"
import type { CountrySummary } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"

type StatusFilter = "all" | "active" | "inactive"

/**
 * Gestion des pays dans le back-office.
 *
 * Réutilise le tableau et le formulaire de la page Pays : dupliquer la saisie
 * d'un pays à deux endroits garantirait qu'ils divergent.
 */
export function CountriesSection() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<CountrySummary | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)

  const query = useQuery(
    JSON.stringify({ section: "pays", page, debouncedSearch, statusFilter }),
    (signal) => {
      const params: Record<string, unknown> = { page, page_size: PAGE_SIZE }
      if (statusFilter !== "all") params.is_active = statusFilter === "active"
      if (debouncedSearch) params.search = debouncedSearch
      return fetchCountries(params, signal)
    },
    { fallback: "Impossible de charger les pays" },
  )

  const afterWrite = () => {
    invalidateReferentiel("countries")
    query.reload()
  }

  const handleSave = async (values: CountryFormValues) => {
    if (editing) {
      await updateCountry(editing.id, values)
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
      afterWrite()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Changement de statut impossible")
    } finally {
      setTogglingId(null)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold">Pays</h2>
        <p className="text-xs text-muted-foreground">
          Identifiant fonctionnel, devise, fuseau horaire. Un pays ne se
          supprime pas : il se désactive, pour que son historique reste lisible.
        </p>
      </div>

      {(query.error || actionError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
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
        canManage
      />

      <Pagination
        page={page}
        count={query.data?.count ?? 0}
        onChange={setPage}
        noun={["pays", "pays"]}
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
        title={editing ? `Modifier ${editing.name}` : "Ajouter un pays"}
      />
    </div>
  )
}
