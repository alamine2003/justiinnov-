import { Plus, Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { CountrySummary } from "@/lib/types"

interface CountryTableProps {
  countries: CountrySummary[]
  loading: boolean
  search: string
  onSearchChange: (value: string) => void
  onFilterStatus: (status: "all" | "active" | "inactive") => void
  statusFilter: "all" | "active" | "inactive"
  onAdd: () => void
  onOpen: (id: number) => void
  onToggle: (country: CountrySummary) => void
  /** Masque les actions que le rôle ne peut pas exécuter. */
  canManage: boolean
}

export function CountryTable({
  countries,
  loading,
  search,
  onSearchChange,
  onFilterStatus,
  statusFilter,
  onAdd,
  onOpen,
  onToggle,
  canManage,
}: CountryTableProps) {
  // La colonne « Actions » n'existe que si le rôle peut agir.
  const columnCount = 7 + (canManage ? 1 : 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Rechercher un pays…"
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border border-border/60 bg-muted/60 p-0.5 shadow-inner shadow-black/5">
            {(["all", "active", "inactive"] as const).map((status) => (
              <Button
                key={status}
                variant="ghost"
                size="sm"
                className={
                  statusFilter === status
                    ? "bg-background shadow-sm text-foreground"
                    : "text-muted-foreground"
                }
                onClick={() => onFilterStatus(status)}
              >
                {status === "all"
                  ? "Tous"
                  : status === "active"
                    ? "Actifs"
                    : "Inactifs"}
              </Button>
            ))}
          </div>
          {canManage && (
            <Button onClick={onAdd}>
              <Plus className="mr-2 h-4 w-4" />
              Ajouter
            </Button>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Pays</TableHead>
              <TableHead>Devise</TableHead>
              <TableHead>Fuseau horaire</TableHead>
              <TableHead className="text-center">Équipes</TableHead>
              <TableHead className="text-center">Centres de coûts</TableHead>
              <TableHead className="text-center">Projets</TableHead>
              <TableHead>Statut</TableHead>
              {canManage && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: columnCount }).map((_, j) => (
                    <TableCell key={j}>
                      <div className="h-4 animate-pulse rounded bg-muted" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : countries.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columnCount} className="h-24 text-center text-muted-foreground">
                  Aucun pays trouvé.
                </TableCell>
              </TableRow>
            ) : (
              countries.map((country) => (
                <TableRow
                  key={country.id}
                  className="cursor-pointer"
                  onClick={() => onOpen(country.id)}
                >
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-sm font-semibold uppercase text-primary shadow-sm shadow-primary/10">
                        {country.code}
                      </div>
                      <div>
                        <p className="font-medium">{country.name}</p>
                        <p className="text-xs text-muted-foreground">{country.timezone}</p>
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
                      <Badge variant="default" className="bg-emerald-500 hover:bg-emerald-500">
                        Actif
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Inactif</Badge>
                    )}
                  </TableCell>
                  {canManage && (
                    <TableCell
                      className="text-right"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Button
                        variant="outline"
                        size="sm"
                        className="shadow-sm"
                        onClick={() => onToggle(country)}
                      >
                        {country.is_active ? "Désactiver" : "Réactiver"}
                      </Button>
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