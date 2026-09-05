import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { AlertTriangle, FileWarning, Paperclip, Search } from "lucide-react"
import { useTranslation } from "react-i18next"
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
import { ExportMenu } from "@/components/reporting/export-menu"
import { useAuth } from "@/context/use-auth"
import { fetchCountries } from "@/lib/countries"
import { fetchRegister } from "@/lib/expenses"
import { WORKFLOW_STATUSES, workflowLabel } from "@/lib/labels"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import type { WorkflowStatus } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"
import { cn, formatAmount, formatDateIn, fromCountryLocalInput } from "@/lib/utils"

/**
 * Filtre « à contrôler » : les lignes soumises ou en contrôle, en une seule
 * valeur pour le sélecteur, transmise au serveur en `status__in`. C'est la
 * tuile du tableau de bord qui y mène.
 */
const TO_REVIEW_FILTER = "submitted,in_review"

/** Filtre de statut lu dans l'URL : un statut, ou le groupe « à contrôler ». */
function readStatusFilter(params: URLSearchParams): WorkflowStatus | typeof TO_REVIEW_FILTER | "" {
  const statusIn = params.get("status__in")
  if (statusIn === TO_REVIEW_FILTER) return TO_REVIEW_FILTER
  const status = params.get("status") ?? ""
  return (WORKFLOW_STATUSES as string[]).includes(status) ? (status as WorkflowStatus) : ""
}

export function RegisterPage() {
  const { t } = useTranslation()
  const { me } = useAuth()
  const [params, setParams] = useSearchParams()

  const statusFilter = readStatusFilter(params)

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search)
  const [countryId, setCountryId] = useState<number | "">("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [exportError, setExportError] = useState<string | null>(null)

  const countries = useReferentiel(
    "countries",
    () => fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: Boolean(me?.has_global_scope) },
  )
  const selectedCountry = countries.data?.results.find((c) => c.id === countryId)
  // Les bornes de période sont des jours du pays filtré : « du 1er au 3 »
  // à Nairobi ne commence pas à la même seconde qu'à Paris. Un compte pays
  // lit dans le fuseau de son pays ; le siège sans pays choisi, dans le sien.
  const timezone =
    selectedCountry?.timezone ??
    (me?.has_global_scope ? null : (me?.countries[0]?.timezone ?? null))

  const query = useQuery(
    JSON.stringify({ page, debouncedSearch, statusFilter, countryId, from, to, timezone }),
    (signal) => {
      const requestParams: Record<string, unknown> = {
        page,
        page_size: PAGE_SIZE,
        ordering: "-date",
      }
      if (debouncedSearch) requestParams.search = debouncedSearch
      if (statusFilter === TO_REVIEW_FILTER) requestParams.status__in = statusFilter
      else if (statusFilter) requestParams.status = statusFilter
      if (countryId !== "") requestParams.country = countryId
      const debut = from ? fromCountryLocalInput(`${from}T00:00`, timezone) : null
      const fin = to ? fromCountryLocalInput(`${to}T23:59:59`, timezone) : null
      if (debut) requestParams.date__gte = debut
      if (fin) requestParams.date__lte = fin
      return fetchRegister(requestParams, signal)
    },
    { fallback: t("registre.chargement_impossible") },
  )

  const entries = query.data?.results ?? []
  const count = query.data?.count ?? 0
  const withoutProof = entries.filter((e) => !e.has_proof).length

  const changeStatus = (value: string) => {
    setPage(1)
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete("status")
        next.delete("status__in")
        if (value === TO_REVIEW_FILTER) next.set("status__in", value)
        else if (value) next.set("status", value)
        return next
      },
      { replace: true },
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("registre.titre")} description={t("registre.description")}>
        {/* Le menu reprend le pays du filtre ; il n'ajoute que l'exercice et le mois. */}
        <ExportMenu country={countryId} onError={setExportError} />
      </PageHeader>

      {(query.error || exportError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{exportError ?? query.error}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={countries.data} noun={t("dossiers.noms_pays")} />

      {withoutProof > 0 && (
        <Alert>
          <FileWarning className="h-4 w-4" />
          <AlertTitle>{t("registre.sans_piece", { count: withoutProof })}</AlertTitle>
          <AlertDescription>{t("registre.sans_piece_aide")}</AlertDescription>
        </Alert>
      )}

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">{t("registre.filtres")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="grid gap-1.5">
              <Label htmlFor="reg-search" className="text-xs">
                {t("registre.recherche")}
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
                  placeholder={t("registre.recherche_placeholder")}
                  className="pl-9"
                />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="reg-status" className="text-xs">
                {t("commun.statut")}
              </Label>
              <NativeSelect
                id="reg-status"
                value={statusFilter}
                onChange={(e) => changeStatus(e.target.value)}
              >
                <option value="">{t("commun.tous")}</option>
                <option value={TO_REVIEW_FILTER}>{t("registre.a_controler")}</option>
                {WORKFLOW_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {workflowLabel(t, value)}
                  </option>
                ))}
              </NativeSelect>
            </div>
            {me?.has_global_scope && (
              <div className="grid gap-1.5">
                <Label htmlFor="reg-country" className="text-xs">
                  {t("commun.pays")}
                </Label>
                <NativeSelect
                  id="reg-country"
                  value={countryId}
                  onChange={(e) => {
                    setCountryId(e.target.value === "" ? "" : Number(e.target.value))
                    setPage(1)
                  }}
                >
                  <option value="">{t("registre.tous_pays")}</option>
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
                {timezone ? t("registre.du_heure", { fuseau: timezone }) : t("registre.du")}
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
                {t("registre.au")}
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
                  <TableHead scope="col">{t("registre.colonnes.date_heure")}</TableHead>
                  <TableHead scope="col">{t("champs.number")}</TableHead>
                  <TableHead scope="col">{t("registre.colonnes.depense")}</TableHead>
                  <TableHead scope="col">{t("champs.place")}</TableHead>
                  <TableHead scope="col">{t("champs.beneficiary")}</TableHead>
                  <TableHead scope="col">{t("registre.colonnes.equipe_manager")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("commun.montant")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("registre.colonnes.justifie")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("registre.colonnes.ecart")}</TableHead>
                  <TableHead scope="col">{t("registre.colonnes.preuve")}</TableHead>
                  <TableHead scope="col">{t("commun.statut")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={11} />
                ) : entries.length === 0 ? (
                  <EmptyRow
                    colSpan={11}
                    icon={FileWarning}
                    title={t("registre.vide.titre")}
                    hint={t("registre.vide.aide")}
                  />
                ) : (
                  entries.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatDateIn(entry.date, entry.country_timezone)}
                        <br />
                        <span className="opacity-70">
                          {t("registre.heure_locale", { fuseau: entry.country_timezone })}
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
                        {entry.place || t("commun.aucun")}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {entry.beneficiary_name ?? t("commun.aucun")}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {entry.team_name ?? t("commun.aucun")}
                        <br />
                        {entry.owner_name || entry.created_by || t("commun.aucun")}
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
                            {t("registre.pieces", { count: entry.proofs.length })}
                            {entry.proofs.some((p) => !p.is_complete) && (
                              <Badge variant="outline" className="ml-1 text-[10px]">
                                {t("registre.incomplet")}
                              </Badge>
                            )}
                          </div>
                        ) : (
                          <Badge variant="outline" className="text-destructive">
                            {t("registre.aucune")}
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
            noun={[t("depenses.nom_one"), t("depenses.nom_other")]}
          />
        </CardContent>
      </Card>
    </div>
  )
}
