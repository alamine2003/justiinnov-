import { useState } from "react"
import { AlertTriangle, Pencil, Plus, Wallet } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { NativeSelect } from "@/components/ui/native-select"
import { StatCard } from "@/components/ui/stat-card"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PageHeader } from "@/components/ui/page-header"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { BudgetForm, type BudgetFormValues } from "@/components/budgets/budget-form"
import { Reallocations } from "@/components/budgets/reallocations"
import { useAuth } from "@/context/use-auth"
import { fetchConfiguration } from "@/lib/accounts"
import {
  createBudget,
  fetchBudgetSummary,
  fetchBudgets,
  updateBudget,
} from "@/lib/budgets"
import { fetchCountries, fetchProjects, fetchTeams } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import type { Budget } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn, formatAmount, formatRate } from "@/lib/utils"

const CURRENT_YEAR = new Date().getFullYear()
const YEARS = [CURRENT_YEAR + 1, CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2]

export function BudgetsPage() {
  const { t } = useTranslation()
  const { can } = useAuth()
  // Attribuer, modifier, arbitrer : trois droits, à la direction par défaut.
  const canCreate = can("budgets.create")
  const canEdit = can("budgets.update")
  const canRequest = can("reallocations.request")
  const canManage = canCreate || canEdit
  // Un seul exercice pour le résumé par pays et la liste des enveloppes :
  // les deux onglets parlent des mêmes chiffres.
  const [year, setYear] = useState(CURRENT_YEAR)

  const query = useQuery(
    `budgets:${year}`,
    async (signal) => {
      const [budgets, summary] = await Promise.all([
        fetchBudgets({ page_size: REFERENTIEL_PAGE_SIZE, year }, signal),
        fetchBudgetSummary({ year }),
      ])
      return { budgets, summary }
    },
    { fallback: t("budgets.erreur_chargement") },
  )
  const budgets = query.data?.budgets.results ?? []
  const summary = query.data?.summary ?? null

  // Le référentiel du formulaire n'est lu que par qui peut attribuer.
  const countries = useReferentiel(
    "countries",
    () => fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
  )
  const projects = useReferentiel(
    "projects",
    () => fetchProjects({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: canManage },
  )
  const teams = useReferentiel(
    "teams",
    () => fetchTeams({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: canManage },
  )
  const configuration = useReferentiel("configuration", fetchConfiguration, {
    enabled: canManage && can("configuration.manage"),
  })

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Budget | null>(null)

  const symbolOf = (countryId: number, fallback: string) =>
    countries.data?.results.find((c) => c.id === countryId)?.currency_symbol || fallback
  const consolidatedSymbol =
    countries.data?.results.find((c) => c.currency === "XOF")?.currency_symbol || "XOF"

  const handleSave = async (values: BudgetFormValues) => {
    if (editing) {
      await updateBudget(editing.id, values)
    } else {
      await createBudget(values)
    }
    setEditing(null)
    query.reload()
  }

  const referentielError = countries.error ?? projects.error ?? teams.error

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("budgets.titre")}
        description={t("budgets.description")}
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
          {canCreate && (
            <Button
              onClick={() => {
                setEditing(null)
                setFormOpen(true)
              }}
            >
              <Plus className="mr-2 h-4 w-4" aria-hidden />
              {t("budgets.attribuer")}
            </Button>
          )}
        </div>
      </PageHeader>

      {(query.error || referentielError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{query.error ?? referentielError}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={query.data?.budgets} noun={t("budgets.noms.enveloppes")} />
      <TruncatedNotice page={countries.data} noun={t("budgets.noms.pays")} />

      {summary && summary.unconverted_currencies.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("budgets.conversion.titre")}</AlertTitle>
          <AlertDescription>
            {t("budgets.conversion.texte", {
              devises: summary.unconverted_currencies.join(", "),
            })}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          icon={Wallet}
          label={t("budgets.indicateurs.disponible_consolide")}
          value={formatAmount(summary?.total_remaining_xof, consolidatedSymbol)}
          hint={t("budgets.indicateurs.taux_en_vigueur")}
        />
        <StatCard
          icon={Wallet}
          label={t("budgets.indicateurs.pays_dotes")}
          value={summary?.countries.length ?? 0}
        />
        <StatCard
          icon={Wallet}
          label={t("budgets.indicateurs.enveloppes")}
          value={query.data?.budgets.count ?? 0}
        />
      </div>

      <Tabs defaultValue="pays">
        <TabsList className="bg-muted/60">
          <TabsTrigger value="pays">{t("budgets.onglets.pays")}</TabsTrigger>
          <TabsTrigger value="enveloppes">{t("budgets.onglets.enveloppes")}</TabsTrigger>
          <TabsTrigger value="reallocations">{t("budgets.onglets.reallocations")}</TabsTrigger>
        </TabsList>

        <TabsContent value="pays" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <div className="overflow-x-auto rounded-lg border border-border/60">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead scope="col">{t("commun.pays")}</TableHead>
                      <TableHead scope="col" className="text-right">{t("budgets.colonnes.enveloppe")}</TableHead>
                      <TableHead scope="col" className="text-right">{t("budgets.colonnes.engage")}</TableHead>
                      <TableHead scope="col" className="text-right">{t("budgets.colonnes.consomme")}</TableHead>
                      <TableHead scope="col" className="text-right">{t("budgets.colonnes.disponible")}</TableHead>
                      <TableHead scope="col" className="text-right">
                        {t("budgets.colonnes.disponible_devise", { devise: consolidatedSymbol })}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {query.loading ? (
                      <SkeletonRows columns={6} />
                    ) : !summary || summary.countries.length === 0 ? (
                      <EmptyRow
                        colSpan={6}
                        icon={Wallet}
                        title={t("budgets.vide.pays_titre")}
                        hint={
                          canCreate
                            ? t("budgets.vide.pays_indication_siege")
                            : t("budgets.vide.pays_indication_pays")
                        }
                      />
                    ) : (
                      summary.countries.map((row) => (
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
                            {Number(row.sub_allocated) > 0 && (
                              <p className="text-xs text-muted-foreground">
                                {t("budgets.dont_reparti", {
                                  montant: formatAmount(row.sub_allocated),
                                })}
                              </p>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            {formatAmount(row.engaged)}
                          </TableCell>
                          <TableCell className="text-right">
                            {formatAmount(row.consumed)}
                          </TableCell>
                          <TableCell
                            className={cn(
                              "text-right font-medium",
                              Number(row.remaining) < 0 && "text-destructive",
                            )}
                          >
                            {formatAmount(row.remaining)}
                          </TableCell>
                          <TableCell className="text-right text-muted-foreground">
                            {row.remaining_xof
                              ? formatAmount(row.remaining_xof)
                              : t("budgets.taux_inconnu")}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="enveloppes" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <div className="overflow-x-auto rounded-lg border border-border/60">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead scope="col">{t("budgets.colonnes.enveloppe")}</TableHead>
                      <TableHead scope="col">{t("commun.annee")}</TableHead>
                      <TableHead scope="col" className="text-right">{t("commun.montant")}</TableHead>
                      <TableHead scope="col" className="text-right">{t("budgets.colonnes.engage")}</TableHead>
                      <TableHead scope="col" className="text-right">{t("budgets.colonnes.disponible")}</TableHead>
                      <TableHead scope="col">{t("budgets.colonnes.execution")}</TableHead>
                      <TableHead scope="col">{t("budgets.colonnes.depassement")}</TableHead>
                      {canEdit && (
                        <TableHead scope="col" className="text-right">{t("commun.actions")}</TableHead>
                      )}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {query.loading ? (
                      <SkeletonRows columns={canEdit ? 8 : 7} />
                    ) : budgets.length === 0 ? (
                      <EmptyRow
                        colSpan={canEdit ? 8 : 7}
                        icon={Wallet}
                        title={t("budgets.vide.enveloppes_titre")}
                        hint={
                          canManage
                            ? t("budgets.vide.enveloppes_indication_siege")
                            : t("budgets.vide.enveloppes_indication_pays")
                        }
                      />
                    ) : (
                      budgets.map((budget) => (
                        <TableRow key={budget.id}>
                          <TableCell>
                            <p className="font-medium">{budget.country_name}</p>
                            <p className="text-xs text-muted-foreground">
                              {budget.scope_label ?? t("budgets.portee.country")}
                              {!budget.is_active && ` · ${t("budgets.inactive")}`}
                            </p>
                          </TableCell>
                          <TableCell>{budget.year}</TableCell>
                          <TableCell className="text-right">
                            {formatAmount(budget.amount, symbolOf(budget.country, budget.currency))}
                          </TableCell>
                          <TableCell className="text-right">
                            {formatAmount(budget.figures.engaged)}
                          </TableCell>
                          <TableCell
                            className={cn(
                              "text-right font-medium",
                              Number(budget.figures.remaining) < 0 && "text-destructive",
                            )}
                          >
                            {formatAmount(budget.figures.remaining)}
                          </TableCell>
                          <TableCell>
                            {formatRate(budget.figures.execution_rate)}
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary">
                              {budget.overrun_policy_display}
                            </Badge>
                          </TableCell>
                          {canEdit && (
                            <TableCell className="text-right">
                              <Button
                                variant="ghost"
                                size="icon"
                                aria-label={t("budgets.modifier_aria", {
                                  pays: budget.country_name,
                                  annee: budget.year,
                                })}
                                onClick={() => {
                                  setEditing(budget)
                                  setFormOpen(true)
                                }}
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                            </TableCell>
                          )}
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reallocations" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <Reallocations
                budgets={budgets}
                canRequest={canRequest}
                onChanged={query.reload}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <BudgetForm
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open)
          if (!open) setEditing(null)
        }}
        onSave={handleSave}
        countries={countries.data?.results ?? []}
        projects={projects.data?.results ?? []}
        teams={teams.data?.results ?? []}
        editing={editing}
        defaultYear={year}
        defaultPolicy={configuration.data?.workflow.default_overrun_policy}
      />
    </div>
  )
}
