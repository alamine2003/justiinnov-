import { Link } from "react-router-dom"
import { Globe, Pencil, Plus, Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { STATUS_TONES } from "@/lib/status-styles"
import type { CountrySummary } from "@/lib/types"

type StatusFilter = "all" | "active" | "inactive"

const FILTER_LABELS: Record<StatusFilter, string> = {
  all: "Tous",
  active: "Actifs",
  inactive: "Inactifs",
}

interface CountryTableProps {
  countries: CountrySummary[]
  loading: boolean
  search: string
  onSearchChange: (value: string) => void
  onFilterStatus: (status: StatusFilter) => void
  statusFilter: StatusFilter
  onAdd: () => void
  onEdit: (country: CountrySummary) => void
  onToggle: (country: CountrySummary) => void
  /** Masque les actions que le rôle ne peut pas exécuter. */
  canManage: boolean
  /** Vrai pendant qu'un changement de statut est en cours pour ce pays. */
  togglingId?: number | null
}

export function CountryTable({
  countries,
  loading,
  search,
  onSearchChange,
  onFilterStatus,
  statusFilter,
  onAdd,
  onEdit,
  onToggle,
  canManage,
  togglingId = null,
}: CountryTableProps) {
  // La colonne « Actions » n'existe que si le rôle peut agir.
  const columnCount = 7 + (canManage ? 1 : 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Rechercher un pays…"
            aria-label="Rechercher un pays"
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-2">
          <fieldset className="inline-flex rounded-lg border border-border/60 bg-muted/60 p-0.5 shadow-inner shadow-black/5">
            <legend className="sr-only">Filtrer par statut</legend>
            {(["all", "active", "inactive"] as const).map((status) => (
              <Button
                key={status}
                variant="ghost"
                size="sm"
                aria-pressed={statusFilter === status}
                className={
                  statusFilter === status
                    ? "bg-background shadow-sm text-foreground"
                    : "text-muted-foreground"
                }
                onClick={() => onFilterStatus(status)}
              >
                {FILTER_LABELS[status]}
              </Button>
            ))}
          </fieldset>
          {canManage && (
            <Button onClick={onAdd}>
              <Plus className="mr-2 h-4 w-4" aria-hidden />
              Ajouter
            </Button>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Pays</TableHead>
              <TableHead scope="col">Devise</TableHead>
              <TableHead scope="col">Fuseau horaire</TableHead>
              <TableHead scope="col" className="text-center">Équipes</TableHead>
              <TableHead scope="col" className="text-center">Centres de coûts</TableHead>
              <TableHead scope="col" className="text-center">Projets</TableHead>
              <TableHead scope="col">Statut</TableHead>
              {canManage && <TableHead scope="col" className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <SkeletonRows columns={columnCount} />
            ) : countries.length === 0 ? (
              <EmptyRow
                colSpan={columnCount}
                icon={Globe}
                title="Aucun pays trouvé"
                hint={
                  canManage
                    ? "Ajoutez un pays depuis la liste des codes ISO d'Afrique."
                    : "Aucun pays ne correspond à ces filtres."
                }
              />
            ) : (
              countries.map((country) => (
                <TableRow key={country.id}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <div
                        aria-hidden
                        className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-sm font-semibold uppercase text-primary shadow-sm shadow-primary/10"
                      >
                        {country.code}
                      </div>
                      <div>
                        {/* Le lien porte la navigation : accessible au
                            clavier, ouvrable dans un nouvel onglet. */}
                        <Link
                          to={`/countries/${country.id}`}
                          className="font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {country.name}
                        </Link>
                        <p className="text-xs text-muted-foreground">{country.country_ref ?? country.code}</p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="font-medium">{country.currency_symbol || country.currency}</span>
                    <span className="ml-1 text-xs text-muted-foreground">
                      {country.currency}
                    </span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{country.timezone}</TableCell>
                  <TableCell className="text-center">{country.team_count}</TableCell>
                  <TableCell className="text-center">{country.cost_center_count}</TableCell>
                  <TableCell className="text-center">{country.project_count}</TableCell>
                  <TableCell>
                    {country.is_active ? (
                      <Badge className={STATUS_TONES.SUCCES}>Actif</Badge>
                    ) : (
                      <Badge variant="secondary">Inactif</Badge>
                    )}
                  </TableCell>
                  {canManage && (
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Modifier ${country.name}`}
                          onClick={() => onEdit(country)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="shadow-sm"
                          disabled={togglingId === country.id}
                          onClick={() => onToggle(country)}
                        >
                          {country.is_active ? "Désactiver" : "Réactiver"}
                        </Button>
                      </div>
                    </TableCell>
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
