import { useState } from "react"
import { AlertTriangle, Pencil, Plus, Wallet } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
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
import { fetchCountries, fetchManagers, fetchProjects, fetchTeams } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import type { Budget } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn, formatAmount, formatRate } from "@/lib/utils"

export function BudgetsPage() {
  const { can } = useAuth()
  const canManage = can("manage_budgets")

  const query = useQuery(
    "budgets",
    async (signal) => {
      const [budgets, summary] = await Promise.all([
        fetchBudgets({ page_size: REFERENTIEL_PAGE_SIZE }, signal),
        fetchBudgetSummary(),
      ])
      return { budgets, summary }
    },
    { fallback: "Impossible de charger les budgets" },
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
  const managers = useReferentiel(
    "managers",
    () => fetchManagers({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: canManage },
  )
  const configuration = useReferentiel("configuration", fetchConfiguration, {
    enabled: canManage && can("manage_users"),
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

  const referentielError = countries.error ?? projects.error ?? teams.error ?? managers.error

  return (
    <div className="space-y-6">
      <PageHeader
        title="Budgets"
        description="Enveloppes annuelles par pays, sous-enveloppes par projet, équipe ou manager, et réallocations."
      >
        {canManage && (
          <Button
            onClick={() => {
              setEditing(null)
              setFormOpen(true)
            }}
          >
            <Plus className="mr-2 h-4 w-4" aria-hidden />
            Attribuer une enveloppe
          </Button>
        )}
      </PageHeader>

      {(query.error || referentielError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{query.error ?? referentielError}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={query.data?.budgets} noun="enveloppes" />
      <TruncatedNotice page={countries.data} noun="pays" />

      {summary && summary.unconverted_currencies.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Conversion incomplète</AlertTitle>
          <AlertDescription>
            Aucun taux connu pour {summary.unconverted_currencies.join(", ")} : ces
            montants sont exclus du total consolidé plutôt que d'y être absorbés.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          icon={Wallet}
          label="Disponible consolidé"
          value={formatAmount(summary?.total_remaining_xof, consolidatedSymbol)}
          hint="Converti au taux en vigueur"
        />
        <StatCard icon={Wallet} label="Pays dotés" value={summary?.countries.length ?? 0} />
        <StatCard icon={Wallet} label="Enveloppes" value={query.data?.budgets.count ?? 0} />
      </div>

      <Tabs defaultValue="pays">
        <TabsList className="bg-muted/60">
          <TabsTrigger value="pays">Par pays</TabsTrigger>
          <TabsTrigger value="enveloppes">Enveloppes</TabsTrigger>
          <TabsTrigger value="reallocations">Réallocations</TabsTrigger>
        </TabsList>

        <TabsContent value="pays" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <div className="overflow-x-auto rounded-lg border border-border/60">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead scope="col">Pays</TableHead>
                      <TableHead scope="col" className="text-right">Enveloppe</TableHead>
                      <TableHead scope="col" className="text-right">Engagé</TableHead>
                      <TableHead scope="col" className="text-right">Consommé</TableHead>
                      <TableHead scope="col" className="text-right">Disponible</TableHead>
                      <TableHead scope="col" className="text-right">Disponible ({consolidatedSymbol})</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {query.loading ? (
                      <SkeletonRows columns={6} />
                    ) : !summary || summary.countries.length === 0 ? (
                      <EmptyRow
                        colSpan={6}
                        icon={Wallet}
                        title="Aucune enveloppe attribuée"
                        hint={
                          canManage
                            ? "Attribuez une enveloppe annuelle à chaque pays suivi."
                            : "Le siège n'a pas encore attribué d'enveloppe à votre périmètre."
                        }
                      />
                    ) : (
                      summary.countries.map((row) => (
                        <TableRow key={row.country}>
                          <TableCell>
                            <p className="font-medium">{row.country_name}</p>
                            <p className="text-xs text-muted-foreground">
                              {row.country_ref ?? "—"} · {symbolOf(row.country, row.currency)}
                            </p>
                          </TableCell>
                          <TableCell className="text-right">
                            {formatAmount(row.allocated)}
                            {Number(row.sub_allocated) > 0 && (
                              <p className="text-xs text-muted-foreground">
                                dont {formatAmount(row.sub_allocated)} réparti
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
                              : "taux inconnu"}
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
                      <TableHead scope="col">Enveloppe</TableHead>
                      <TableHead scope="col">Année</TableHead>
                      <TableHead scope="col" className="text-right">Montant</TableHead>
                      <TableHead scope="col" className="text-right">Engagé</TableHead>
                      <TableHead scope="col" className="text-right">Disponible</TableHead>
                      <TableHead scope="col">Exécution</TableHead>
                      <TableHead scope="col">Dépassement</TableHead>
                      {canManage && <TableHead scope="col" className="text-right">Actions</TableHead>}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {query.loading ? (
                      <SkeletonRows columns={canManage ? 8 : 7} />
                    ) : budgets.length === 0 ? (
                      <EmptyRow
                        colSpan={canManage ? 8 : 7}
                        icon={Wallet}
                        title="Aucune enveloppe"
                        hint={
                          canManage
                            ? "Attribuez une enveloppe pour commencer le suivi."
                            : "Aucune enveloppe sur votre périmètre."
                        }
                      />
                    ) : (
                      budgets.map((budget) => (
                        <TableRow key={budget.id}>
                          <TableCell>
                            <p className="font-medium">{budget.country_name}</p>
                            <p className="text-xs text-muted-foreground">
                              {budget.scope_label ?? "Enveloppe du pays"}
                              {!budget.is_active && " · inactive"}
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
                          {canManage && (
                            <TableCell className="text-right">
                              <Button
                                variant="ghost"
                                size="icon"
                                aria-label={`Modifier l'enveloppe ${budget.country_name} ${budget.year}`}
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
                canDecide={canManage}
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
        managers={managers.data?.results ?? []}
        editing={editing}
        defaultPolicy={configuration.data?.workflow.default_overrun_policy}
      />
    </div>
  )
}
