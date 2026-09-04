import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
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
import { OriginalAmount } from "@/components/expenses/original-amount"
import { StatusBadge } from "@/components/expenses/status-badge"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { PageHeader } from "@/components/ui/page-header"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { useAuth } from "@/context/use-auth"
import { fetchCountries } from "@/lib/countries"
import { fetchRegister } from "@/lib/expenses"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import { WORKFLOW_LABELS, type WorkflowStatus } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"
import {
  cn,
  formatAmount,
  formatDateIn,
  fromCountryLocalInput,
  pluralize,
} from "@/lib/utils"

const STATUSES = Object.keys(WORKFLOW_LABELS) as WorkflowStatus[]

export function RegisterPage() {
  const { me } = useAuth()
  const [params, setParams] = useSearchParams()

  const statusParam = params.get("status") ?? ""
  const statusFilter = (STATUSES as string[]).includes(statusParam)
    ? (statusParam as WorkflowStatus)
    : ""

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search)
  const [countryId, setCountryId] = useState<number | "">("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")

  const countries = useReferentiel(
    "countries",
    () => fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: Boolean(me?.has_global_scope) },
  )
  const selectedCountry = countries.data?.results.find((c) => c.id === countryId)
  // Les bornes de période sont des jours du pays filtré : « du 1er au 3 »
  // à Nairobi ne commence pas à la même seconde qu'à Paris. Sans pays, ce
  // sont des jours locaux du lecteur.
  const timezone = selectedCountry?.timezone ?? null

  const query = useQuery(
    JSON.stringify({ page, debouncedSearch, statusFilter, countryId, from, to, timezone }),
    (signal) => {
      const requestParams: Record<string, unknown> = {
        page,
        page_size: PAGE_SIZE,
        ordering: "-date",
      }
      if (debouncedSearch) requestParams.search = debouncedSearch
      if (statusFilter) requestParams.status = statusFilter
      if (countryId !== "") requestParams.country = countryId
      const debut = from ? fromCountryLocalInput(`${from}T00:00`, timezone) : null
      const fin = to ? fromCountryLocalInput(`${to}T23:59:59`, timezone) : null
      if (debut) requestParams.date__gte = debut
      if (fin) requestParams.date__lte = fin
      return fetchRegister(requestParams, signal)
    },
    { fallback: "Impossible de charger le registre" },
  )

  const entries = query.data?.results ?? []
  const count = query.data?.count ?? 0
  const withoutProof = entries.filter((e) => !e.has_proof).length

  const changeStatus = (value: string) => {
    setPage(1)
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set("status", value)
        else next.delete("status")
        return next
      },
      { replace: true },
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Registre de justification"
        description="Où est passé l'argent : chaque dépense avec sa date, son lieu, son bénéficiaire — et la pièce qui l'atteste."
      />

      {query.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{query.error}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={countries.data} noun="pays" />

      {withoutProof > 0 && (
        <Alert>
          <FileWarning className="h-4 w-4" />
          <AlertTitle>
            {pluralize(withoutProof, "dépense sans pièce", "dépenses sans pièce")} sur cette page
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
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input
                  id="reg-search"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(1)
                  }}
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
                onChange={(e) => changeStatus(e.target.value)}
              >
                <option value="">Tous</option>
                {STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {WORKFLOW_LABELS[value]}
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
                  onChange={(e) => {
                    setCountryId(e.target.value === "" ? "" : Number(e.target.value))
                    setPage(1)
                  }}
                >
                  <option value="">Tous les pays</option>
                  {(countries.data?.results ?? []).map((country) => (
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
                Du{timezone ? ` (heure ${timezone})` : ""}
              </Label>
              <Input
                id="reg-from"
                type="date"
                value={from}
                onChange={(e) => {
                  setFrom(e.target.value)
                  setPage(1)
                }}
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
                onChange={(e) => {
                  setTo(e.target.value)
                  setPage(1)
                }}
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
                  <TableHead scope="col">Date et heure (locale)</TableHead>
                  <TableHead scope="col">N°ORDRE</TableHead>
                  <TableHead scope="col">Dépense</TableHead>
                  <TableHead scope="col">Lieu</TableHead>
                  <TableHead scope="col">Bénéficiaire</TableHead>
                  <TableHead scope="col">Équipe / Manager</TableHead>
                  <TableHead scope="col" className="text-right">Montant</TableHead>
                  <TableHead scope="col" className="text-right">Justifié</TableHead>
                  <TableHead scope="col" className="text-right">Écart</TableHead>
                  <TableHead scope="col">Preuve</TableHead>
                  <TableHead scope="col">Statut</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={11} />
                ) : entries.length === 0 ? (
                  <EmptyRow
                    colSpan={11}
                    icon={FileWarning}
                    title="Aucune dépense sur ce périmètre"
                    hint="Élargissez la période ou retirez un filtre."
                  />
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
                          className="font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                        {entry.owner_name || entry.created_by || "—"}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {formatAmount(entry.amount, entry.currency)}
                        <OriginalAmount
                          currency={entry.original_currency}
                          amount={entry.original_amount}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(entry.justified_amount)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right",
                          Number(entry.gap) > 0 && "font-medium text-destructive",
                        )}
                      >
                        {formatAmount(entry.gap)}
                      </TableCell>
                      <TableCell>
                        {entry.has_proof ? (
                          <div className="flex items-center gap-1 text-xs">
                            <Paperclip className="h-3 w-3 text-muted-foreground" aria-hidden />
                            {pluralize(entry.proofs.length, "pièce")}
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
                        <StatusBadge status={entry.status} label={entry.status_display} />
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
            noun={["dépense", "dépenses"]}
          />
        </CardContent>
      </Card>
    </div>
  )
}
