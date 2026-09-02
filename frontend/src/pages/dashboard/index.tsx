import { useCallback, useEffect, useState } from "react"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAuth } from "@/context/auth"
import { fetchCountries } from "@/lib/countries"
import {
  downloadExport,
  fetchBreakdown,
  fetchDashboard,
  type ExportKind,
} from "@/lib/reporting"
import type {
  AlertLevel,
  Breakdown,
  BreakdownRow,
  CountrySummary,
  Dashboard,
} from "@/lib/types"
import { formatAmount, formatRate } from "@/lib/utils"

const LEVEL_STYLE: Record<AlertLevel, string> = {
  info: "bg-blue-500 hover:bg-blue-500",
  warning: "bg-amber-500 hover:bg-amber-500",
  critical: "bg-destructive hover:bg-destructive",
}

const CURRENT_YEAR = new Date().getFullYear()
const YEARS = [CURRENT_YEAR + 1, CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2]

export function DashboardPage() {
  const { me } = useAuth()
  const [year, setYear] = useState(CURRENT_YEAR)
  const [countryId, setCountryId] = useState<number | "">("")
  const [countries, setCountries] = useState<CountrySummary[]>([])
  const [data, setData] = useState<Dashboard | null>(null)
  const [breakdown, setBreakdown] = useState<Breakdown | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState<ExportKind | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const params: Record<string, unknown> = { year }
    if (countryId !== "") params.country = countryId
    try {
      const [dashboard, detail, countryPage] = await Promise.all([
        fetchDashboard(params),
        fetchBreakdown(params),
        fetchCountries({ page_size: 200 }),
      ])
      setData(dashboard)
      setBreakdown(detail)
      setCountries(countryPage.results)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger le tableau de bord")
    } finally {
      setLoading(false)
    }
  }, [year, countryId])

  useEffect(() => {
    void load()
  }, [load])

  const runExport = async (kind: ExportKind) => {
    setExporting(kind)
    setError(null)
    try {
      const params: Record<string, unknown> = { year }
      if (countryId !== "") params.country = countryId
      await downloadExport(kind, params)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export impossible")
    } finally {
      setExporting(null)
    }
  }

  if (loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pilotage</h1>
          <p className="text-sm text-muted-foreground">
            {me?.has_global_scope
              ? "Consolidation de tous les pays, convertie en FCFA."
              : "Consommation et alertes de votre périmètre."}
          </p>
        </div>
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
              {countries.map((country) => (
                <option key={country.id} value={country.id}>
                  {country.country_ref ? `${country.country_ref} — ` : ""}
                  {country.name}
                </option>
              ))}
            </NativeSelect>
          )}
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

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
        <Stat
          label="Enveloppe"
          value={formatAmount(data?.totals.allocated)}
          hint={`${formatAmount(data?.consolidated_xof.allocated)} FCFA consolidés`}
        />
        <Stat
          label="Consommé"
          value={formatAmount(data?.totals.consumed)}
          hint={`Taux d'exécution ${formatRate(data?.totals.execution_rate)}`}
        />
        <Stat
          label="Engagé"
          value={formatAmount(data?.totals.engaged)}
          hint="Soumis ou en contrôle"
        />
        <Stat
          label="Sans preuve"
          value={formatAmount(data?.totals.gap)}
          hint={`Justifié à ${formatRate(data?.totals.justification_rate)}`}
        />
        <Stat
          label="Disponible"
          value={formatAmount(data?.totals.remaining)}
          hint={`${formatAmount(data?.consolidated_xof.remaining)} FCFA`}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Workload
          label="À contrôler"
          value={data?.workload.expenses_to_review ?? 0}
          to="/dossiers?status=submitted"
        />
        <Workload label="Brouillons" value={data?.workload.expenses_draft ?? 0} to="/dossiers" />
        <Workload
          label="Non justifiées"
          value={data?.workload.expenses_unjustified ?? 0}
          to="/dossiers?status=unjustified"
        />
        <Workload label="Dossiers ouverts" value={data?.workload.dossiers_open ?? 0} to="/dossiers" />
      </div>

      {data && data.alerts.length > 0 && (
        <Card className="border-border/60 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">
              Alertes ({data.alerts.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.alerts.slice(0, 12).map((alert) => (
              <Link
                key={alert.key}
                to={alert.link || "/dossiers"}
                className="flex items-start gap-3 rounded-lg border border-border/60 p-3 transition-colors hover:bg-accent/30"
              >
                <Badge className={LEVEL_STYLE[alert.level]}>
                  {alert.level === "critical" ? "Critique" : "Alerte"}
                </Badge>
                <div className="min-w-0">
                  <p className="text-sm font-medium">{alert.title}</p>
                  <p className="text-xs text-muted-foreground">{alert.detail}</p>
                </div>
              </Link>
            ))}
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
          <div className="overflow-hidden rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pays</TableHead>
                  <TableHead className="text-right">Enveloppe</TableHead>
                  <TableHead className="text-right">Engagé</TableHead>
                  <TableHead className="text-right">Consommé</TableHead>
                  <TableHead className="text-right">Justifié</TableHead>
                  <TableHead className="text-right">Sans preuve</TableHead>
                  <TableHead className="text-right">Disponible</TableHead>
                  <TableHead>Exécution</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!data || data.countries.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                      Aucune enveloppe sur la période.
                    </TableCell>
                  </TableRow>
                ) : (
                  data.countries.map((row) => (
                    <TableRow key={row.country}>
                      <TableCell>
                        <p className="font-medium">{row.country_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {row.country_ref ?? "—"} · {row.currency}
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
                      <TableCell className="text-right">
                        {Number(row.gap) > 0 ? (
                          <span className="font-medium text-destructive">
                            {formatAmount(row.gap)}
                          </span>
                        ) : (
                          formatAmount(row.gap)
                        )}
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

function Stat({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          <TrendingUp className="h-3.5 w-3.5" />
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold tracking-tight">{value}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
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
      className="flex items-center justify-between rounded-lg border border-border/60 bg-card p-4 shadow-sm transition-colors hover:bg-accent/30"
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
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div
          className={
            over
              ? "h-full bg-destructive"
              : near
                ? "h-full bg-amber-500"
                : "h-full bg-emerald-500"
          }
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">{formatRate(rate)}</span>
    </div>
  )
}

function BreakdownTable({ rows }: { rows: BreakdownRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Aucune dépense sur la période.
      </p>
    )
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border/60">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Libellé</TableHead>
            <TableHead className="text-center">Lignes</TableHead>
            <TableHead className="text-right">Dépenses</TableHead>
            <TableHead className="text-right">Justifié</TableHead>
            <TableHead className="text-right">Écart</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.label}>
              <TableCell className="font-medium">{row.label}</TableCell>
              <TableCell className="text-center">{row.lines}</TableCell>
              <TableCell className="text-right">{formatAmount(row.amount)}</TableCell>
              <TableCell className="text-right">{formatAmount(row.justified)}</TableCell>
              <TableCell className="text-right">{formatAmount(row.gap)}</TableCell>
            </TableRow>
          ))}
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
      onClick={() => onExport(kind)}
    >
      {busy === kind ? (
        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
      ) : (
        <Icon className="mr-1 h-4 w-4" />
      )}
      {label}
    </Button>
  )
}
