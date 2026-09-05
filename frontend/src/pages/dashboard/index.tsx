import { useState } from "react"
import { Link } from "react-router-dom"
import { AlertTriangle, Loader2, TrendingUp } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { NativeSelect } from "@/components/ui/native-select"
import { PageHeader } from "@/components/ui/page-header"
import { StatCard } from "@/components/ui/stat-card"
import { EmptyRow } from "@/components/ui/table-states"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { ExportMenu } from "@/components/reporting/export-menu"
import { useAuth } from "@/context/use-auth"
import { fetchConfiguration } from "@/lib/accounts"
import { fetchCountries } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import { executionWarningRate, fetchBreakdown, fetchDashboard } from "@/lib/reporting"
import { alertLevelLabel } from "@/lib/labels"
import { ALERT_LEVEL_STYLE } from "@/lib/status-styles"
import type { BreakdownRow } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn, formatAmount, formatRate } from "@/lib/utils"

/** Alertes montrées d'emblée ; le reste est signalé par un compte. */
const VISIBLE_ALERTS = 12


const CURRENT_YEAR = new Date().getFullYear()
const YEARS = [CURRENT_YEAR + 1, CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2]

export function DashboardPage() {
  const { t } = useTranslation()
  const { me, can } = useAuth()
  const [year, setYear] = useState(CURRENT_YEAR)
  const [countryId, setCountryId] = useState<number | "">("")
  const [exportError, setExportError] = useState<string | null>(null)

  const countries = useReferentiel(
    "countries",
    () => fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: Boolean(me?.has_global_scope) },
  )
  // Les seuils d'alerte de la configuration colorent la barre d'exécution ;
  // la configuration n'est lisible que par les administrateurs.
  const configuration = useReferentiel("configuration", fetchConfiguration, {
    enabled: can("configuration.manage"),
  })
  const warningRate = executionWarningRate(configuration.data?.alertes.seuils)
  const query = useQuery(
    JSON.stringify({ year, countryId }),
    async (signal) => {
      const params: Record<string, unknown> = { year }
      if (countryId !== "") params.country = countryId
      // La répartition n'a de sens que pour un pays : sans pays choisi, le
      // serveur la refuse à un compte siège (deux équipes homonymes de pays
      // différents fusionneraient). Un compte restreint à un pays l'obtient
      // sans le nommer.
      const repartitionPossible = countryId !== "" || !me?.has_global_scope
      const [dashboard, breakdown] = await Promise.all([
        fetchDashboard(params, signal),
        repartitionPossible ? fetchBreakdown(params, signal) : Promise.resolve(null),
      ])
      return { dashboard, breakdown }
    },
    { fallback: t("pilotage.erreur_chargement") },
  )
  const data = query.data?.dashboard ?? null
  const breakdown = query.data?.breakdown ?? null
  const symbolOf = (id: number, fallback: string) =>
    countries.data?.results.find((c) => c.id === id)?.currency_symbol || fallback
  // La consolidation se fait en XOF ; le symbole vient du premier pays qui
  // l'utilise, pour ne pas écrire « FCFA » en dur à côté d'un « XOF ».
  const consolidatedSymbol =
    countries.data?.results.find((c) => c.currency === "XOF")?.currency_symbol || "XOF"

  if (query.loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center" aria-busy="true">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="sr-only">{t("pilotage.chargement")}</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("pilotage.titre")}
        description={
          me?.has_global_scope
            ? t("pilotage.description_siege", { devise: consolidatedSymbol })
            : t("pilotage.description_pays")
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <NativeSelect
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            aria-label={t("commun.annee")}
            className="w-28"
          >
            {YEARS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </NativeSelect>
          {me?.has_global_scope && (
            <NativeSelect
              value={countryId}
              onChange={(e) =>
                setCountryId(e.target.value === "" ? "" : Number(e.target.value))
              }
              aria-label={t("commun.pays")}
              className="w-48"
            >
              <option value="">{t("pilotage.tous_pays")}</option>
              {(countries.data?.results ?? []).map((country) => (
                <option key={country.id} value={country.id}>
                  {country.country_ref ? `${country.country_ref} — ` : ""}
                  {country.name}
                </option>
              ))}
            </NativeSelect>
          )}
          {query.refreshing && (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label={t("pilotage.actualisation")} />
          )}
          {/* Le menu reprend l'exercice et le pays des filtres ci-dessus ; il
              n'ajoute que le mois. */}
          <ExportMenu year={year} country={countryId} onError={setExportError} />
        </div>
      </PageHeader>

      {(query.error || exportError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{exportError ?? query.error}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={countries.data} noun={t("pilotage.noms.pays")} />

      {data && data.consolidated_xof.unconverted_currencies.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("pilotage.conversion.titre")}</AlertTitle>
          <AlertDescription>
            {t("pilotage.conversion.texte", {
              devises: data.consolidated_xof.unconverted_currencies.join(", "),
            })}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          icon={TrendingUp}
          label={t("pilotage.indicateurs.enveloppe")}
          value={formatAmount(data?.totals.allocated)}
          hint={t("pilotage.indicateurs.consolides", {
            montant: formatAmount(data?.consolidated_xof.allocated, consolidatedSymbol),
          })}
        />
        <StatCard
          icon={TrendingUp}
          label={t("pilotage.indicateurs.consomme")}
          value={formatAmount(data?.totals.consumed)}
          hint={t("pilotage.indicateurs.taux_execution", {
            taux: formatRate(data?.totals.execution_rate),
          })}
        />
        <StatCard
          icon={TrendingUp}
          label={t("pilotage.indicateurs.engage")}
          value={formatAmount(data?.totals.engaged)}
          hint={t("pilotage.indicateurs.soumis_ou_controle")}
        />
        <StatCard
          icon={TrendingUp}
          label={t("pilotage.indicateurs.sans_preuve")}
          value={formatAmount(data?.totals.gap)}
          hint={t("pilotage.indicateurs.justifie_a", {
            taux: formatRate(data?.totals.justification_rate),
          })}
        />
        <StatCard
          icon={TrendingUp}
          label={t("pilotage.indicateurs.disponible")}
          value={formatAmount(data?.totals.remaining)}
          hint={formatAmount(data?.consolidated_xof.remaining, consolidatedSymbol)}
        />
      </div>

      {/* Les trois premiers comptes portent sur des lignes : ils mènent au
          registre, filtré sur le même statut. Le dernier compte des
          dossiers. */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Workload
          label={t("pilotage.charge.a_controler")}
          value={data?.workload.expenses_to_review ?? 0}
          to="/registre?status__in=submitted,in_review"
        />
        <Workload
          label={t("pilotage.charge.brouillon")}
          value={data?.workload.expenses_draft ?? 0}
          to="/registre?status=draft"
        />
        <Workload
          label={t("pilotage.charge.non_justifiees")}
          value={data?.workload.expenses_unjustified ?? 0}
          to="/registre?status=unjustified"
        />
        <Workload
          label={t("pilotage.charge.dossiers_ouverts")}
          value={data?.workload.dossiers_open ?? 0}
          to="/dossiers"
        />
      </div>

      {data && data.alerts.length > 0 && (
        <Card className="border-border/60 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">
              {t("pilotage.alertes", { count: data.alerts_total })}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.alerts.slice(0, VISIBLE_ALERTS).map((alert) => (
              <Link
                key={alert.key}
                to={alert.link || "/dossiers"}
                className="flex items-start gap-3 rounded-lg border border-border/60 p-3 transition-colors hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Badge className={ALERT_LEVEL_STYLE[alert.level]}>
                  {alertLevelLabel(t, alert.level)}
                </Badge>
                <div className="min-w-0">
                  <p className="text-sm font-medium">{alert.title}</p>
                  <p className="text-xs text-muted-foreground">{alert.detail}</p>
                </div>
              </Link>
            ))}
            {data.alerts_total > VISIBLE_ALERTS && (
              <p className="pt-1 text-xs text-muted-foreground">
                {t("pilotage.autres_alertes", {
                  count: data.alerts_total - VISIBLE_ALERTS,
                })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">{t("pilotage.par_pays")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">{t("commun.pays")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("pilotage.colonnes.enveloppe")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("pilotage.colonnes.engage")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("pilotage.colonnes.consomme")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("pilotage.colonnes.justifie")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("pilotage.colonnes.sans_preuve")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("pilotage.colonnes.disponible")}</TableHead>
                  <TableHead scope="col">{t("pilotage.colonnes.execution")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!data || data.countries.length === 0 ? (
                  <EmptyRow
                    colSpan={8}
                    icon={TrendingUp}
                    title={t("pilotage.vide.pays_titre")}
                    hint={t("pilotage.vide.pays_indication")}
                  />
                ) : (
                  data.countries.map((row) => (
                    <TableRow key={row.country}>
                      <TableCell>
                        <p className="font-medium">{row.country_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {row.country_ref ?? t("commun.aucun")} ·{" "}
                          {symbolOf(row.country, row.currency)}
                        </p>
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(row.allocated)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(row.engaged)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(row.consumed)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(row.justified)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right",
                          Number(row.gap) > 0 && "font-medium text-destructive",
                        )}
                      >
                        {formatAmount(row.gap)}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {formatAmount(row.remaining)}
                      </TableCell>
                      <TableCell>
                        <ExecutionBar rate={row.execution_rate} warningRate={warningRate} />
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {!breakdown && !query.loading && me?.has_global_scope && (
        <p className="text-sm text-muted-foreground">
          {t("pilotage.choisir_pays")}
        </p>
      )}

      {breakdown && (
        <Card className="border-border/60 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">{t("pilotage.repartition.titre")}</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="by_month">
              <TabsList className="flex w-full flex-wrap justify-start bg-muted/60">
                <TabsTrigger value="by_month">{t("pilotage.repartition.par_mois")}</TabsTrigger>
                <TabsTrigger value="by_team">{t("pilotage.repartition.par_equipe")}</TabsTrigger>
                <TabsTrigger value="by_owner">{t("pilotage.repartition.par_manager")}</TabsTrigger>
                <TabsTrigger value="by_project">{t("pilotage.repartition.par_projet")}</TabsTrigger>
                <TabsTrigger value="by_category">{t("pilotage.repartition.par_categorie")}</TabsTrigger>
                <TabsTrigger value="by_expense_title">
                  {t("pilotage.repartition.par_intitule")}
                </TabsTrigger>
              </TabsList>
              {(
                [
                  "by_month", "by_team", "by_owner",
                  "by_project", "by_category", "by_expense_title",
                ] as const
              ).map((key) => (
                <TabsContent key={key} value={key} className="mt-4">
                  <BreakdownTable rows={breakdown[key]} />
                </TabsContent>
              ))}
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function Workload({
  label,
  value,
  to,
}: {
  label: string
  value: number
  to: string
}) {
  return (
    <Link
      to={to}
      className="flex items-center justify-between rounded-lg border border-border/60 bg-card p-4 shadow-sm transition-colors hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-xl font-semibold">{value}</span>
    </Link>
  )
}

function ExecutionBar({ rate, warningRate }: { rate: string | null; warningRate: number }) {
  const value = rate ? Math.min(Number(rate) * 100, 100) : 0
  const over = rate ? Number(rate) > 1 : false
  const near = rate ? Number(rate) >= warningRate : false
  return (
    <div className="flex items-center gap-2">
      <div aria-hidden className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div
          className={
            over
              ? "h-full bg-destructive"
              : near
                ? "h-full bg-statut-attente"
                : "h-full bg-statut-succes"
          }
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">{formatRate(rate)}</span>
    </div>
  )
}

function BreakdownTable({ rows }: { rows: BreakdownRow[] }) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto rounded-lg border border-border/60">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">{t("pilotage.repartition.colonnes.libelle")}</TableHead>
            <TableHead scope="col" className="text-center">{t("pilotage.repartition.colonnes.lignes")}</TableHead>
            <TableHead scope="col" className="text-right">{t("pilotage.repartition.colonnes.depenses")}</TableHead>
            <TableHead scope="col" className="text-right">{t("pilotage.repartition.colonnes.justifie")}</TableHead>
            <TableHead scope="col" className="text-right">{t("pilotage.repartition.colonnes.ecart")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <EmptyRow
              colSpan={5}
              title={t("pilotage.repartition.vide_titre")}
              hint={t("pilotage.repartition.vide_indication")}
            />
          ) : (
            rows.map((row) => (
              <TableRow key={row.label}>
                <TableCell className="font-medium">{row.label}</TableCell>
                <TableCell className="text-center">{row.lines}</TableCell>
                <TableCell className="text-right">{formatAmount(row.amount)}</TableCell>
                <TableCell className="text-right">{formatAmount(row.justified)}</TableCell>
                <TableCell
                  className={cn("text-right", Number(row.gap) > 0 && "font-medium text-destructive")}
                >
                  {formatAmount(row.gap)}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
