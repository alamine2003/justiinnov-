import { useCallback, useEffect, useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { AlertTriangle, FolderOpen, Loader2, Plus, Search } from "lucide-react"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { PageHeader } from "@/components/ui/page-header"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import { StatusBadge } from "@/components/expenses/status-badge"
import { useAuth } from "@/context/auth"
import { createDossier, fetchDossiers } from "@/lib/expenses"
import { fetchCountries, fetchTeams } from "@/lib/countries"
import {
  WORKFLOW_LABELS,
  type CountrySummary,
  type Dossier,
  type Team,
  type WorkflowStatus,
} from "@/lib/types"
import { formatAmount } from "@/lib/utils"

export function DossiersPage() {
  const navigate = useNavigate()
  const { can } = useAuth()
  const canCreate = can("record_expenses")

  const [dossiers, setDossiers] = useState<Dossier[]>([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [countries, setCountries] = useState<CountrySummary[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<WorkflowStatus | "">("")
  const [formOpen, setFormOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, unknown> = { page, page_size: PAGE_SIZE }
      if (search) params.search = search
      if (statusFilter) params.status = statusFilter
      const [dossierPage, countryPage, teamPage] = await Promise.all([
        fetchDossiers(params),
        fetchCountries({ page_size: 200 }),
        fetchTeams({ page_size: 200 }),
      ])
      setDossiers(dossierPage.results)
      setCount(dossierPage.count)
      setCountries(countryPage.results)
      setTeams(teamPage.results)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger les dossiers")
    } finally {
      setLoading(false)
    }
  }, [page, search, statusFilter])

  useEffect(() => {
    void load()
  }, [load])

  // Un changement de filtre ramène à la première page : rester en page 4
  // d'un résultat qui n'en compte plus qu'une afficherait un tableau vide.
  useEffect(() => {
    setPage(1)
  }, [search, statusFilter])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dossiers de justification"
        description="Un dossier porte un N°ORDRE et regroupe les dépenses et les preuves d'une même opération."
      >
        {canCreate && (
          <Button onClick={() => setFormOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Nouveau dossier
          </Button>
        )}
      </PageHeader>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="N°ORDRE ou libellé…"
            className="pl-9"
          />
        </div>
        <NativeSelect
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as WorkflowStatus | "")}
          className="sm:max-w-[12rem]"
          aria-label="Filtrer par statut"
        >
          <option value="">Tous les statuts</option>
          {Object.entries(WORKFLOW_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </div>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <div className="overflow-hidden rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>N°ORDRE</TableHead>
                  <TableHead>Pays</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead className="text-center">Lignes</TableHead>
                  <TableHead className="text-center">Preuves</TableHead>
                  <TableHead className="text-right">Dépenses</TableHead>
                  <TableHead className="text-right">Écart</TableHead>
                  <TableHead>Statut</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <SkeletonRows columns={8} />
                ) : dossiers.length === 0 ? (
                  <EmptyRow
                    colSpan={8}
                    icon={FolderOpen}
                    title="Aucun dossier"
                    hint={
                      canCreate
                        ? "Créez un dossier pour y rattacher vos dépenses."
                        : "Aucun dossier ne correspond à ces filtres."
                    }
                  />
                ) : (
                  dossiers.map((dossier) => (
                    <TableRow
                      key={dossier.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/dossiers/${dossier.id}`)}
                    >
                      <TableCell>
                        <p className="font-medium">{dossier.number}</p>
                        <p className="text-xs text-muted-foreground">{dossier.label}</p>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {dossier.country_ref ?? dossier.country_name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {new Date(dossier.date).toLocaleDateString("fr-FR")}
                      </TableCell>
                      <TableCell className="text-center">{dossier.expense_count}</TableCell>
                      <TableCell className="text-center">{dossier.proof_count}</TableCell>
                      <TableCell className="text-right">
                        {formatAmount(dossier.totals.amount, dossier.currency)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(dossier.totals.gap)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={dossier.status} />
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
            noun={["dossier", "dossiers"]}
          />
        </CardContent>
      </Card>

      <DossierForm
        open={formOpen}
        onOpenChange={setFormOpen}
        countries={countries}
        teams={teams}
        onSaved={load}
      />
    </div>
  )
}

function DossierForm({
  open,
  onOpenChange,
  countries,
  teams,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  countries: CountrySummary[]
  teams: Team[]
  onSaved: () => Promise<void>
}) {
  const [number, setNumber] = useState("")
  const [label, setLabel] = useState("")
  const [country, setCountry] = useState<number | "">("")
  const [team, setTeam] = useState<number | "">("")
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setNumber("")
    setLabel("")
    setCountry(countries[0]?.id ?? "")
    setTeam("")
    setDate(new Date().toISOString().slice(0, 10))
    setError(null)
  }, [open, countries])

  const eligibleTeams = teams.filter((t) => t.country === country)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await createDossier({
        number,
        label,
        country,
        team: team === "" ? null : team,
        date,
      })
      await onSaved()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Création impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nouveau dossier</DialogTitle>
          <DialogDescription>
            Le N°ORDRE identifie l'ensemble documentaire ; il doit être unique.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2">
          {error && (
            <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="dos-number">N°ORDRE</Label>
              <Input
                id="dos-number"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
                placeholder="N-2026-001"
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dos-date">Date</Label>
              <Input
                id="dos-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="dos-label">Libellé</Label>
            <Input
              id="dos-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Mission commerciale Lomé"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="dos-country">Pays</Label>
              <NativeSelect
                id="dos-country"
                value={country}
                onChange={(e) => {
                  setCountry(Number(e.target.value))
                  setTeam("")
                }}
              >
                {countries.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.country_ref ? `${c.country_ref} — ` : ""}
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dos-team">Équipe</Label>
              <NativeSelect
                id="dos-team"
                value={team}
                onChange={(e) =>
                  setTeam(e.target.value === "" ? "" : Number(e.target.value))
                }
              >
                <option value="">—</option>
                {eligibleTeams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Annuler
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Créer
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
