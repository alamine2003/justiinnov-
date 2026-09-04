import { useState } from "react"
import { Link } from "react-router-dom"
import {
  AlertTriangle,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  TrendingUp,
} from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { useAuth } from "@/context/use-auth"
import { fetchCountries } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import {
  downloadExport,
  fetchBreakdown,
  fetchDashboard,
  type ExportKind,
} from "@/lib/reporting"
import { ALERT_LEVEL_STYLE } from "@/lib/status-styles"
import { ALERT_LEVEL_LABELS, type BreakdownRow } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn, formatAmount, formatRate, pluralize } from "@/lib/utils"

/** Alertes montrées d'emblée ; le reste est signalé par un compte. */
const VISIBLE_ALERTS = 12

const CURRENT_YEAR = new Date().getFullYear()
const YEARS = [CURRENT_YEAR + 1, CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2]

export function DashboardPage() {
  const { me } = useAuth()
  const [year, setYear] = useState(CURRENT_YEAR)
  const [countryId, setCountryId] = useState<number | "">("")
  const [exporting, setExporting] = useState<ExportKind | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const countries = useReferentiel(
    "countries",
    () => fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: Boolean(me?.has_global_scope) },
  )
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
    { fallback: "Impossible de charger le tableau de bord" },
  )
  const data = query.data?.dashboard ?? null
  const breakdown = query.data?.breakdown ?? null
  const symbolOf = (id: number, fallback: string) =>
    countries.data?.results.find((c) => c.id === id)?.currency_symbol || fallback
  // La consolidation se fait en XOF ; le symbole vient du premier pays qui
  // l'utilise, pour ne pas écrire « FCFA » en dur à côté d'un « XOF ».
  const consolidatedSymbol =
    countries.data?.results.find((c) => c.currency === "XOF")?.currency_symbol || "XOF"

  const runExport = async (kind: ExportKind) => {
    setExporting(kind)
    setExportError(null)
    try {
      const params: Record<string, unknown> = { year }
      if (countryId !== "") params.country = countryId
      await downloadExport(kind, params)
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export impossible")
    } finally {
      setExporting(null)
    }
  }

  if (query.loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center" aria-busy="true">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="sr-only">Chargement du tableau de bord…</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Pilotage"
        description={
          me?.has_global_scope
            ? `Consolidation de tous les pays, convertie en ${consolidatedSymbol}.`
            : "Consommation et alertes de votre périmètre."
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <NativeSelect
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            aria-label="Année"
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
              aria-label="Pays"
              className="w-48"
            >
              <option value="">Tous les pays</option>
              {(countries.data?.results ?? []).map((country) => (
                <option key={country.id} value={country.id}>
                  {country.country_ref ? `${country.country_ref} — ` : ""}
                  {country.name}
                </option>
              ))}
            </NativeSelect>
          )}
          {query.refreshing && (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Actualisation" />
          )}
        </div>
      </PageHeader>

      {(query.error || exportError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{exportError ?? query.error}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={countries.data} noun="pays" />

      {data && data.consolidated_xof.unconverted_currencies.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Conversion incomplète</AlertTitle>
          <AlertDescription>
            Aucun taux connu pour{" "}
            {data.consolidated_xof.unconverted_currencies.join(", ")} : ces
            montants sont exclus du total consolidé.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          icon={TrendingUp}
          label="Enveloppe"
          value={formatAmount(data?.totals.allocated)}
          hint={`${formatAmount(data?.consolidated_xof.allocated, consolidatedSymbol)} consolidés`}
        />
        <StatCard
          icon={TrendingUp}
          label="Consommé"
          value={formatAmount(data?.totals.consumed)}
          hint={`Taux d'exécution ${formatRate(data?.totals.execution_rate)}`}
        />
        <StatCard
          icon={TrendingUp}
          label="Engagé"
          value={formatAmount(data?.totals.engaged)}
          hint="Soumis ou en contrôle"
        />
        <StatCard
          icon={TrendingUp}
          label="Sans preuve"
          value={formatAmount(data?.totals.gap)}
          hint={`Justifié à ${formatRate(data?.totals.justification_rate)}`}
        />
        <StatCard
          icon={TrendingUp}
          label="Disponible"
          value={formatAmount(data?.totals.remaining)}
          hint={formatAmount(data?.consolidated_xof.remaining, consolidatedSymbol)}
        />
      </div>

      {/* Les trois premiers comptes portent sur des lignes : ils mènent au
          registre, filtré sur le même statut. Le dernier compte des
          dossiers. */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Workload
          label="Lignes à contrôler"
          value={data?.workload.expenses_to_review ?? 0}
          to="/registre?status=submitted"
        />
        <Workload
          label="Lignes en brouillon"
          value={data?.workload.expenses_draft ?? 0}
          to="/registre?status=draft"
        />
        <Workload
          label="Lignes non justifiées"
          value={data?.workload.expenses_unjustified ?? 0}
          to="/registre?status=unjustified"
        />
        <Workload label="Dossiers ouverts" value={data?.workload.dossiers_open ?? 0} to="/dossiers" />
      </div>

      {data && data.alerts.length > 0 && (
        <Card className="border-border/60 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">
              {pluralize(data.alerts_total, "alerte")}
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
                  {ALERT_LEVEL_LABELS[alert.level]}
                </Badge>
                <div className="min-w-0">
                  <p className="text-sm font-medium">{alert.title}</p>
                  <p className="text-xs text-muted-foreground">{alert.detail}</p>
                </div>
              </Link>
            ))}
            {data.alerts_total > VISIBLE_ALERTS && (
              <p className="pt-1 text-xs text-muted-foreground">
                {pluralize(data.alerts_total - VISIBLE_ALERTS, "autre alerte")} — les
                plus graves sont affichées en premier.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle className="text-sm font-semibold">Par pays</CardTitle>
          <div className="flex flex-wrap gap-2">
            <ExportButton
              icon={FileSpreadsheet}
              label="Dépenses"
              kind="expenses.xlsx"
              busy={exporting}
              onExport={runExport}
            />
            <ExportButton
              icon={FileSpreadsheet}
              label="Rapprochement"
              kind="reconciliation.xlsx"
              busy={exporting}
              onExport={runExport}
            />
            <ExportButton
              icon={FileText}
              label="Rapport PDF"
              kind="report.pdf"
              busy={exporting}
              onExport={runExport}
            />
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Pays</TableHead>
                  <TableHead scope="col" className="text-right">Enveloppe</TableHead>
                  <TableHead scope="col" className="text-right">Engagé</TableHead>
                  <TableHead scope="col" className="text-right">Consommé</TableHead>
                  <TableHead scope="col" className="text-right">Justifié</TableHead>
                  <TableHead scope="col" className="text-right">Sans preuve</TableHead>
                  <TableHead scope="col" className="text-right">Disponible</TableHead>
                  <TableHead scope="col">Exécution</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!data || data.countries.length === 0 ? (
                  <EmptyRow
                    colSpan={8}
                    icon={TrendingUp}
                    title="Aucune enveloppe sur la période"
                    hint="Attribuez une enveloppe depuis la page Budgets pour suivre la consommation."
                  />
                ) : (
                  data.countries.map((row) => (
                    <TableRow key={row.country}>
                      <TableCell>
                        <p className="font-medium">{row.country_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {row.country_ref ?? "—"} · {symbolOf(row.country, row.currency)}
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
                        <ExecutionBar rate={row.execution_rate} />
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
          Choisissez un pays pour afficher sa répartition par mois, équipe,
          manager, projet, catégorie et intitulé.
        </p>
      )}

      {breakdown && (
        <Card className="border-border/60 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Répartition</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="by_month">
              <TabsList className="flex w-full flex-wrap justify-start bg-muted/60">
                <TabsTrigger value="by_month">Par mois</TabsTrigger>
                <TabsTrigger value="by_team">Par équipe</TabsTrigger>
                <TabsTrigger value="by_owner">Par manager</TabsTrigger>
                <TabsTrigger value="by_project">Par projet</TabsTrigger>
                <TabsTrigger value="by_category">Par catégorie</TabsTrigger>
                <TabsTrigger value="by_expense_title">Par intitulé</TabsTrigger>
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

function ExecutionBar({ rate }: { rate: string | null }) {
  const value = rate ? Math.min(Number(rate) * 100, 100) : 0
  const over = rate ? Number(rate) > 1 : false
  const near = rate ? Number(rate) >= 0.8 : false
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
  return (
    <div className="overflow-x-auto rounded-lg border border-border/60">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Libellé</TableHead>
            <TableHead scope="col" className="text-center">Lignes</TableHead>
            <TableHead scope="col" className="text-right">Dépenses</TableHead>
            <TableHead scope="col" className="text-right">Justifié</TableHead>
            <TableHead scope="col" className="text-right">Écart</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <EmptyRow
              colSpan={5}
              title="Aucune dépense sur la période"
              hint="Changez d'année ou de pays pour voir une répartition."
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

function ExportButton({
  icon: Icon,
  label,
  kind,
  busy,
  onExport,
}: {
  icon: typeof Download
  label: string
  kind: ExportKind
  busy: ExportKind | null
  onExport: (kind: ExportKind) => Promise<void>
}) {
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={busy !== null}
      onClick={() => void onExport(kind)}
    >
      {busy === kind ? (
        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
      ) : (
        <Icon className="mr-1 h-4 w-4" aria-hidden />
      )}
      {label}
    </Button>
  )
}
