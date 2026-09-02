import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { AlertTriangle } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { CountryForm, type CountryFormValues } from "@/components/countries/country-form"
import { CountryTable } from "@/components/countries/country-table"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import {
  createCountry,
  fetchCountries,
  updateCountry,
} from "@/lib/countries"
import { useAuth } from "@/context/auth"
import type { CountrySummary } from "@/lib/types"

export function CountriesPage() {
  const navigate = useNavigate()
  const { can } = useAuth()
  const canManage = can("manage_countries")
  const [countries, setCountries] = useState<CountrySummary[]>([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all")
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<CountrySummary | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, unknown> = { page, page_size: PAGE_SIZE }
      if (statusFilter !== "all") params.is_active = statusFilter === "active"
      if (search) params.search = search
      const data = await fetchCountries(params)
      setCountries(data.results)
      setCount(data.count)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger les pays")
    } finally {
      setLoading(false)
    }
  }, [page, search, statusFilter])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    setPage(1)
  }, [search, statusFilter])

  const handleSave = async (values: CountryFormValues) => {
    if (editing) {
      await updateCountry(editing.id, values)
    } else {
      await createCountry(values)
    }
    await load()
    setEditing(null)
  }

  const handleToggle = async (country: CountrySummary) => {
    await updateCountry(country.id, { is_active: !country.is_active })
    await load()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Gestion des pays</h1>
        <p className="text-muted-foreground text-sm">
          Définissez la devise, le fuseau horaire et les rattachements de chaque pays.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <CountryTable
        countries={countries}
        loading={loading}
        search={search}
        onSearchChange={setSearch}
        onFilterStatus={setStatusFilter}
        statusFilter={statusFilter}
        onAdd={() => {
          setEditing(null)
          setFormOpen(true)
        }}
        onOpen={(id) => navigate(`/countries/${id}`)}
        onToggle={handleToggle}
        canManage={canManage}
      />

      <Pagination
        page={page}
        count={count}
        onChange={setPage}
        noun={["pays", "pays"]}
      />

      <CountryForm
        open={formOpen}
        onOpenChange={setFormOpen}
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