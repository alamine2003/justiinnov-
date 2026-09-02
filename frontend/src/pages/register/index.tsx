import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { AlertTriangle, FileWarning, Paperclip, Search } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { StatusBadge } from "@/components/expenses/status-badge"
import { useAuth } from "@/context/auth"
import { fetchCountries } from "@/lib/countries"
import { fetchRegister } from "@/lib/expenses"
import {
  WORKFLOW_LABELS,
  type CountrySummary,
  type RegisterEntry,
  type WorkflowStatus,
} from "@/lib/types"
import { formatAmount, formatDateIn } from "@/lib/utils"

/** Nombre de lignes par page — aligné sur la pagination du serveur. */
const PAGE_SIZE = 50

export function RegisterPage() {
  const { me } = useAuth()
  const [entries, setEntries] = useState<RegisterEntry[]>([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [countries, setCountries] = useState<CountrySummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<WorkflowStatus | "">("")
  const [countryId, setCountryId] = useState<number | "">("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, unknown> = {
        page,
        page_size: PAGE_SIZE,
        ordering: "-date",
      }
      if (search) params.search = search
      if (statusFilter) params.status = statusFilter
      if (countryId !== "") params.country = countryId
      if (from) params.date__gte = `${from}T00:00:00Z`
      if (to) params.date__lte = `${to}T23:59:59Z`

      const [registerPage, countryPage] = await Promise.all([
        fetchRegister(params),
        fetchCountries({ page_size: 200 }),
      ])
      setEntries(registerPage.results)
      setCount(registerPage.count)
      setCountries(countryPage.results)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger le registre")
    } finally {
      setLoading(false)
    }
  }, [page, search, statusFilter, countryId, from, to])

  useEffect(() => {
    void load()
  }, [load])

  // Tout changement de filtre ramène à la première page : rester en page 4
  // d'un résultat qui n'en compte plus qu'une afficherait un tableau vide.
  useEffect(() => {
    setPage(1)
  }, [search, statusFilter, countryId, from, to])

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))
  const withoutProof = entries.filter((e) => !e.has_proof).length

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Registre de justification
        </h1>
        <p className="text-sm text-muted-foreground">
          Où est passé l'argent : chaque dépense avec sa date, son lieu, son
          bénéficiaire — et la pièce qui l'atteste.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {withoutProof > 0 && (
        <Alert>
          <FileWarning className="h-4 w-4" />
          <AlertTitle>
            {withoutProof} dépense(s) sans pièce sur cette page
          </AlertTitle>
          <AlertDescription>
            Un décaissement sans justificatif reste au débit du budget.
          </AlertDescription>
        </Alert>
      )}

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">Filtres</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="grid gap-1.5">
              <Label htmlFor="reg-search" className="text-xs">
                Recherche
              </Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="reg-search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Libellé, lieu, N°ORDRE…"
                  className="pl-9"
                />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="reg-status" className="text-xs">
                Statut
              </Label>
              <NativeSelect
                id="reg-status"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as WorkflowStatus | "")}
              >
                <option value="">Tous</option>
                {Object.entries(WORKFLOW_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </div>
            {me?.has_global_scope && (
              <div className="grid gap-1.5">
                <Label htmlFor="reg-country" className="text-xs">
                  Pays
                </Label>
                <NativeSelect
                  id="reg-country"
                  value={countryId}
                  onChange={(e) =>
                    setCountryId(e.target.value === "" ? "" : Number(e.target.value))
                  }
                >
                  <option value="">Tous les pays</option>
                  {countries.map((country) => (
                    <option key={country.id} value={country.id}>
                      {country.country_ref ? `${country.country_ref} — ` : ""}
                      {country.name}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            )}
            <div className="grid gap-1.5">
              <Label htmlFor="reg-from" className="text-xs">
                Du
              </Label>
              <Input
                id="reg-from"
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="reg-to" className="text-xs">
                Au
              </Label>
              <Input
                id="reg-to"
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date et heure (locale)</TableHead>
                  <TableHead>N°ORDRE</TableHead>
                  <TableHead>Dépense</TableHead>
                  <TableHead>Lieu</TableHead>
                  <TableHead>Bénéficiaire</TableHead>
                  <TableHead>Équipe / Manager</TableHead>
                  <TableHead className="text-right">Montant</TableHead>
                  <TableHead className="text-right">Justifié</TableHead>
                  <TableHead className="text-right">Écart</TableHead>
                  <TableHead>Preuve</TableHead>
                  <TableHead>Statut</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={11} className="h-16">
                      <div className="h-4 animate-pulse rounded bg-muted" />
                    </TableCell>
                  </TableRow>
                ) : entries.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={11} className="h-24 text-center text-muted-foreground">
                      Aucune dépense sur ce périmètre.
                    </TableCell>
                  </TableRow>
                ) : (
                  entries.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatDateIn(entry.date, entry.country_timezone)}
                        <br />
                        <span className="opacity-70">
                          heure locale · {entry.country_timezone}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Link
                          to={`/dossiers/${entry.dossier}`}
                          className="font-medium hover:underline"
                        >
                          {entry.dossier_number}
                        </Link>
                        <p className="text-xs text-muted-foreground">
                          {entry.country_name}
                        </p>
                      </TableCell>
                      <TableCell>
                        <p className="font-medium">{entry.title}</p>
                        <p className="text-xs text-muted-foreground">
                          {[
                            entry.project_name,
                            entry.expense_title_label,
                            entry.payment_method_display,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {entry.place || "—"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {entry.beneficiary_name ?? "—"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {entry.team_name ?? "—"}
                        <br />
                        {entry.owner_name ?? entry.created_by ?? "—"}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {formatAmount(entry.amount, entry.currency)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(entry.justified_amount)}
                      </TableCell>
                      <TableCell className="text-right">
                        {Number(entry.gap) > 0 ? (
                          <span className="font-medium text-destructive">
                            {formatAmount(entry.gap)}
                          </span>
                        ) : (
                          formatAmount(entry.gap)
                        )}
                      </TableCell>
                      <TableCell>
                        {entry.has_proof ? (
                          <div className="flex items-center gap-1 text-xs">
                            <Paperclip className="h-3 w-3 text-muted-foreground" />
                            {entry.proofs.length}
                            {entry.proofs.some((p) => !p.is_complete) && (
                              <Badge variant="outline" className="ml-1 text-[10px]">
                                incomplet
                              </Badge>
                            )}
                          </div>
                        ) : (
                          <Badge variant="outline" className="text-destructive">
                            aucune
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={entry.status} />
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <Pagination
            page={page}
            totalPages={totalPages}
            count={count}
            onChange={setPage}
          />
        </CardContent>
      </Card>
    </div>
  )
}

function Pagination({
  page,
  totalPages,
  count,
  onChange,
}: {
  page: number
  totalPages: number
  count: number
  onChange: (page: number) => void
}) {
  return (
    <div className="mt-4 flex items-center justify-between text-sm">
      <span className="text-muted-foreground">
        {count} dépense{count > 1 ? "s" : ""} · page {page} sur {totalPages}
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
          className="rounded-lg border border-border/60 px-3 py-1.5 transition-colors hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
        >
          Précédent
        </button>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
          className="rounded-lg border border-border/60 px-3 py-1.5 transition-colors hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
        >
          Suivant
        </button>
      </div>
    </div>
  )
}
