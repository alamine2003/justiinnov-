import { useState } from "react"
import { Link } from "react-router-dom"
import { AlertTriangle, Loader2, TrendingUp } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  BarreEnveloppe,
  CourbeMensuelle,
  JaugeDouble,
  Legende,
  type PointMensuel,
} from "@/components/ui/charts"
import { echelleCommune } from "@/lib/echelle"
import { NativeSelect } from "@/components/ui/native-select"
import { PageHeader } from "@/components/ui/page-header"
import { RefreshIndicator } from "@/components/ui/refresh-indicator"
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
import { isCancelled } from "@/lib/api"
import { fetchCountries } from "@/lib/countries"
import { MONTHS } from "@/lib/months"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import { fetchBreakdown, fetchDashboard } from "@/lib/reporting"
import { alertLevelLabel, notificationKindIcon } from "@/lib/labels"
import { EXECUTION_LEVEL_TEXT } from "@/lib/status-styles"
import type {
  BreakdownRow,
  Dashboard,
  DashboardAlert,
  DashboardCountryRow,
} from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn, currentYear, formatAmount, formatRate, yearChoices } from "@/lib/utils"

/** Alertes montrées d'emblée ; le reste est signalé par un compte. */
const VISIBLE_ALERTS = 12

/**
 * Les douze mois de l'exercice, dans l'ordre, à partir des seuls mois que le
 * serveur a renvoyés (« 2026-03 »). Un mois sans dépense vaut zéro : une
 * courbe qui saute des mois se lit de travers.
 */
function serieMensuelle(rows: BreakdownRow[]): PointMensuel[] {
  const parMois = new Map(rows.map((row) => [Number(row.label.slice(-2)), row]))
  return MONTHS.map((month) => {
    const row = parMois.get(month)
    return {
      month,
      amount: Number(row?.amount ?? 0),
      justified: Number(row?.justified ?? 0),
    }
  })
}

export function DashboardPage() {
  const { t } = useTranslation()
  const { me } = useAuth()
  // Lus au rendu, jamais figés dans le module : une application restée
  // ouverte au passage de l'an proposait encore l'ancien exercice.
  const [year, setYear] = useState(currentYear)
  const years = yearChoices({ before: 2, after: 1 }).reverse()
  const [countryId, setCountryId] = useState<number | "">("")
  const [exportError, setExportError] = useState<string | null>(null)

  const countries = useReferentiel(
    "countries",
    () => fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: Boolean(me?.has_global_scope) },
  )
  // Les pays que ce compte peut nommer : le référentiel au siège, son
  // périmètre sinon. Un compte restreint à plusieurs pays a besoin du
  // sélecteur, sans quoi il ne peut pas obtenir sa répartition.
  const perimetre = me?.countries ?? []
  const paysChoisissables = me?.has_global_scope ? (countries.data?.results ?? []) : perimetre
  const choixPaysVisible = Boolean(me?.has_global_scope) || perimetre.length > 1
  const query = useQuery(
    // Le périmètre entre dans la clé : il décide si la répartition peut être
    // demandée sans nommer de pays, et il n'est connu qu'une fois le profil
    // chargé — sans lui, un compte à pays unique resterait sans répartition.
    JSON.stringify({ year, countryId, perimetre: perimetre.length, global: me?.has_global_scope }),
    async (signal) => {
      const params: Record<string, unknown> = { year }
      if (countryId !== "") params.country = countryId
      // La répartition n'a de sens que pour un pays : sans pays choisi, le
      // serveur la refuse (deux équipes homonymes de pays différents
      // fusionneraient). Il ne devine le pays que lorsque le périmètre n'en
      // compte qu'un — `_pays_unique`, reporting/views.py. Un manager
      // rattaché à deux pays doit donc en nommer un : la demander sans pays
      // rapportait un 400 qui, dans un `Promise.all`, emportait tout le
      // tableau de bord — et le sélecteur de pays lui était masqué.
      const repartitionPossible = countryId !== "" || perimetre.length === 1
      const [dashboard, breakdown] = await Promise.all([
        fetchDashboard(params, signal),
        repartitionPossible
          ? fetchBreakdown(params, signal).catch((e: unknown) => {
              // Un refus sur la répartition laisse le reste de la page debout.
              if (isCancelled(e)) throw e
              return null
            })
          : Promise.resolve(null),
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
            {years.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </NativeSelect>
          {choixPaysVisible && (
            <NativeSelect
              value={countryId}
              onChange={(e) =>
                setCountryId(e.target.value === "" ? "" : Number(e.target.value))
              }
              aria-label={t("commun.pays")}
              className="w-48"
            >
              <option value="">{t("pilotage.tous_pays")}</option>
              {paysChoisissables.map((country) => (
                <option key={country.id} value={country.id}>
                  {country.country_ref ? `${country.country_ref} — ` : ""}
                  {country.name}
                </option>
              ))}
            </NativeSelect>
          )}
          {query.refreshing && <RefreshIndicator label={t("pilotage.actualisation")} />}
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

      {data && <BandeauConsolide data={data} devise={consolidatedSymbol} annee={year} />}

      {/* Les trois premiers comptes portent sur des lignes : ils mènent au
          registre, filtré sur le même statut. Le dernier compte des
          dossiers. */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Charge
          label={t("pilotage.charge.a_controler")}
          hint={t("pilotage.charge.aide.a_controler")}
          value={data?.workload.expenses_to_review ?? 0}
          tone="border-l-statut-attente"
          to="/registre?status__in=submitted,in_review"
        />
        <Charge
          label={t("pilotage.charge.brouillon")}
          hint={t("pilotage.charge.aide.brouillon")}
          value={data?.workload.expenses_draft ?? 0}
          tone="border-l-statut-neutre"
          to="/registre?status=draft"
        />
        <Charge
          label={t("pilotage.charge.non_justifiees")}
          hint={t("pilotage.charge.aide.non_justifiees")}
          value={data?.workload.expenses_unjustified ?? 0}
          tone="border-l-destructive"
          alarme={(data?.workload.expenses_unjustified ?? 0) > 0}
          to="/registre?status=unjustified"
        />
        <Charge
          label={t("pilotage.charge.dossiers_ouverts")}
          hint={t("pilotage.charge.aide.dossiers_ouverts")}
          value={data?.workload.dossiers_open ?? 0}
          tone="border-l-marque"
          to="/dossiers"
        />
      </div>

      {breakdown && (
        <Card className="border-border/60 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="text-sm font-semibold">
                  {t("pilotage.courbe.titre")}
                </CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("pilotage.courbe.description")}
                </p>
              </div>
              <Legende
                items={[
                  { tone: "bg-marque", label: t("pilotage.courbe.depense") },
                  { tone: "border-marque-fort", label: t("pilotage.courbe.justifie"), dashed: true },
                ]}
              />
            </div>
          </CardHeader>
          <CardContent>
            <CourbeMensuelle
              points={serieMensuelle(breakdown.by_month)}
              title={t("pilotage.courbe.aria", { annee: year })}
            />
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <ParPays rows={data?.countries ?? []} symbolOf={symbolOf} />
        <Alertes
          alerts={data?.alerts ?? []}
          total={data?.alerts_total ?? 0}
        />
      </div>

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
            {/* La courbe ci-dessus dit déjà les mois : l'onglet s'ouvre sur
                les équipes, et « par mois » reste là pour les chiffres. */}
            <Tabs defaultValue="by_team">
              <TabsList className="flex w-full flex-wrap justify-start bg-muted/60">
                <TabsTrigger value="by_team">{t("pilotage.repartition.par_equipe")}</TabsTrigger>
                <TabsTrigger value="by_owner">{t("pilotage.repartition.par_manager")}</TabsTrigger>
                <TabsTrigger value="by_project">{t("pilotage.repartition.par_projet")}</TabsTrigger>
                <TabsTrigger value="by_category">{t("pilotage.repartition.par_categorie")}</TabsTrigger>
                <TabsTrigger value="by_expense_title">
                  {t("pilotage.repartition.par_intitule")}
                </TabsTrigger>
                <TabsTrigger value="by_month">{t("pilotage.repartition.par_mois")}</TabsTrigger>
              </TabsList>
              {(
                [
                  "by_team", "by_owner", "by_project",
                  "by_category", "by_expense_title", "by_month",
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

/**
 * Le bandeau marine : l'enveloppe consolidée en gros, ses quatre parts en
 * ligne, et la double jauge exécution / justification. C'est l'ancre visuelle
 * de l'écran — le seul aplat sombre de l'application.
 */
function BandeauConsolide({
  data,
  devise,
  annee,
}: {
  data: Dashboard
  devise: string
  annee: number
}) {
  const { t } = useTranslation()
  const { totals } = data
  const parts = [
    { label: t("pilotage.indicateurs.consomme"), value: totals.consumed, tone: "" },
    { label: t("pilotage.indicateurs.engage"), value: totals.engaged, tone: "" },
    {
      label: t("pilotage.indicateurs.disponible"),
      value: totals.remaining,
      tone: "text-banniere-accent",
    },
    {
      label: t("pilotage.indicateurs.sans_preuve"),
      value: totals.gap,
      tone: Number(totals.gap) > 0 ? "text-destructive" : "",
    },
  ]

  return (
    <section className="rounded-xl bg-banniere px-6 py-5 text-banniere-foreground">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 flex-1 space-y-4">
          <div>
            <p className="text-[0.625rem] font-medium uppercase tracking-[0.1em] text-banniere-muted">
              {t("pilotage.bandeau.titre", { annee })}
            </p>
            <p className="mt-2 flex flex-wrap items-baseline gap-2">
              <span className="text-4xl font-semibold tracking-tight">
                {formatAmount(totals.allocated)}
              </span>
              <span className="text-sm font-medium text-banniere-muted">{devise}</span>
            </p>
          </div>
          <dl className="flex flex-wrap items-stretch gap-x-6 gap-y-3">
            {parts.map((part, index) => (
              <div key={part.label} className="flex items-stretch gap-6">
                {index > 0 && <span aria-hidden className="w-px bg-banniere-bordure" />}
                <div>
                  <dt className="text-[0.5938rem] font-medium uppercase tracking-[0.08em] text-banniere-muted">
                    {part.label}
                  </dt>
                  <dd className={cn("mt-1.5 text-base font-semibold", part.tone)}>
                    {formatAmount(part.value)}
                  </dd>
                </div>
              </div>
            ))}
          </dl>
        </div>

        <div className="flex items-center gap-5">
          <JaugeDouble
            executionRate={totals.execution_rate}
            justificationRate={totals.justification_rate}
            label={formatRate(totals.execution_rate)}
            caption={t("pilotage.bandeau.jauge_legende")}
            title={t("pilotage.bandeau.jauge_aria", {
              execution: formatRate(totals.execution_rate),
              justification: formatRate(totals.justification_rate),
            })}
          />
          <div className="space-y-2">
            <Legende
              className="flex-col items-start gap-2 [&>span]:text-banniere-muted"
              items={[
                {
                  tone: "bg-marque",
                  label: t("pilotage.indicateurs.taux_execution", {
                    taux: formatRate(totals.execution_rate),
                  }),
                },
                {
                  tone: "bg-banniere-accent",
                  label: t("pilotage.indicateurs.justifie_a", {
                    taux: formatRate(totals.justification_rate),
                  }),
                },
              ]}
            />
            {totals.unconverted_currencies.length > 0 && (
              <p className="max-w-[12rem] text-[0.625rem] leading-snug text-banniere-muted">
                {t("pilotage.conversion.texte", {
                  devises: totals.unconverted_currencies.join(", "),
                })}
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

/** Un compte de lignes à traiter, lié au registre filtré sur le même statut. */
function Charge({
  label,
  hint,
  value,
  tone,
  to,
  alarme = false,
}: {
  label: string
  hint: string
  value: number
  tone: string
  to: string
  alarme?: boolean
}) {
  return (
    <Link
      to={to}
      className={cn(
        "flex items-center justify-between gap-3 rounded-lg border border-l-[3px] border-border/60 bg-card p-4 shadow-sm transition-colors hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        tone,
      )}
    >
      <span className="min-w-0">
        <span className="block text-sm text-muted-foreground">{label}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground/80">{hint}</span>
      </span>
      <span
        className={cn(
          "text-2xl font-semibold tracking-tight",
          alarme && "text-destructive",
        )}
      >
        {value}
      </span>
    </Link>
  )
}

/**
 * Chaque pays en barre horizontale, à l'échelle de la plus grande enveloppe :
 * le trait vertical marque l'attribué, et ce qui le franchit vire au corail.
 * Les chiffres restent sous la barre — la forme se voit, les montants se
 * lisent.
 */
function ParPays({
  rows,
  symbolOf,
}: {
  rows: DashboardCountryRow[]
  symbolOf: (id: number, fallback: string) => string
}) {
  const { t } = useTranslation()
  const echelle = echelleCommune(rows)

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-sm font-semibold">{t("pilotage.par_pays")}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("pilotage.barres.description")}
            </p>
          </div>
          <Legende
            items={[
              { tone: "bg-marque", label: t("pilotage.colonnes.consomme") },
              { tone: "bg-marque-clair", label: t("pilotage.colonnes.engage") },
              { tone: "bg-muted", label: t("pilotage.colonnes.disponible") },
            ]}
          />
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/60 p-6 text-center">
            <p className="text-sm font-medium">{t("pilotage.vide.pays_titre")}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("pilotage.vide.pays_indication")}
            </p>
          </div>
        ) : (
          <ul className="space-y-4">
            {rows.map((row) => {
              const attribue = Number(row.allocated)
              // Le dépassement est le disponible du serveur passé sous zéro.
              // Le déduire d'une soustraction maison (`consomme - attribue`)
              // le faisait diverger d'`execution_rate`, qui compte l'engagé :
              // 120 % s'affichait en corail sans aucun montant en regard.
              const depassement = -Number(row.remaining)
              return (
                <li key={row.country}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <span className="flex items-baseline gap-2">
                      <span className="text-sm font-semibold">{row.country_name}</span>
                      <span className="text-xs text-muted-foreground">
                        {row.country_ref ?? t("commun.aucun")} ·{" "}
                        {symbolOf(row.country, row.currency)}
                      </span>
                    </span>
                    <span className="flex items-baseline gap-2.5 text-xs">
                      {depassement > 0 && (
                        <span className="font-medium text-destructive">
                          {t("pilotage.barres.depassement", {
                            montant: formatAmount(String(depassement)),
                          })}
                        </span>
                      )}
                      {/* Le serveur a comparé le taux aux seuils d'alerte
                          (`execution_level`) : un manager et un administrateur
                          lisent la même teinte, sans lire la configuration. */}
                      <span
                        className={cn("font-semibold", EXECUTION_LEVEL_TEXT[row.execution_level])}
                      >
                        {formatRate(row.execution_rate)}
                      </span>
                      <span className="text-muted-foreground">
                        {t("pilotage.barres.attribues", { montant: formatAmount(row.allocated) })}
                      </span>
                    </span>
                  </div>
                  <div className="mt-1.5">
                    <BarreEnveloppe
                      consumed={Number(row.consumed)}
                      engaged={Number(row.engaged)}
                      allocated={attribue}
                      scale={echelle}
                      title={t("pilotage.barres.aria", {
                        pays: row.country_name,
                        taux: formatRate(row.execution_rate),
                      })}
                    />
                  </div>
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    {t("pilotage.barres.detail", {
                      consomme: formatAmount(row.consumed),
                      engage: formatAmount(row.engaged),
                      justifie: formatAmount(row.justified),
                      disponible: formatAmount(row.remaining),
                    })}
                    {Number(row.gap) > 0 && (
                      <span className="font-medium text-destructive">
                        {" · "}
                        {t("pilotage.barres.sans_preuve", { montant: formatAmount(row.gap) })}
                      </span>
                    )}
                  </p>
                </li>
              )
            })}
          </ul>
        )}
        <p className="mt-4 border-t border-border/60 pt-3 text-xs text-muted-foreground">
          {t("pilotage.barres.echelle")}
        </p>
      </CardContent>
    </Card>
  )
}

/** Les alertes les plus graves, teintées par niveau et menant à leur objet. */
function Alertes({ alerts, total }: { alerts: DashboardAlert[]; total: number }) {
  const { t } = useTranslation()
  if (alerts.length === 0) return null

  const TEINTE: Record<DashboardAlert["level"], string> = {
    critical: "border-destructive/30 bg-destructive/5 text-destructive",
    warning: "border-statut-attente/40 bg-statut-attente/10 text-statut-attente",
    info: "border-border/60 text-marque-fort",
  }

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex items-baseline justify-between gap-2">
          <CardTitle className="text-sm font-semibold">
            {t("pilotage.alertes", { count: total })}
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            {t("pilotage.alertes_soustitre")}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {alerts.slice(0, VISIBLE_ALERTS).map((alert) => {
          const Icone = notificationKindIcon(alert.kind) ?? AlertTriangle
          return (
            <Link
              key={alert.key}
              to={alert.link || "/dossiers"}
              className={cn(
                "flex items-start gap-2.5 rounded-lg border p-3 transition-colors hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                TEINTE[alert.level],
              )}
            >
              <Icone className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">{alert.title}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">{alert.detail}</span>
                <span className="sr-only">{alertLevelLabel(t, alert.level)}</span>
              </span>
            </Link>
          )
        })}
        {total > VISIBLE_ALERTS && (
          <p className="pt-1 text-xs text-muted-foreground">
            {t("pilotage.autres_alertes", { count: total - VISIBLE_ALERTS })}
          </p>
        )}
      </CardContent>
    </Card>
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
              icon={TrendingUp}
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
