import { useCallback, useEffect, useState } from "react"
import { AlertTriangle, Pencil, Plus, Wallet } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { BudgetForm, type BudgetFormValues } from "@/components/budgets/budget-form"
import { Reallocations } from "@/components/budgets/reallocations"
import { useAuth } from "@/context/auth"
import {
  createBudget,
  fetchBudgetSummary,
  fetchBudgets,
  updateBudget,
} from "@/lib/budgets"
import { fetchCountries, fetchProjects } from "@/lib/countries"
import type {
  Budget,
  BudgetSummary,
  CountrySummary,
  Project,
} from "@/lib/types"
import { formatAmount, formatRate } from "@/lib/utils"

export function BudgetsPage() {
  const { can } = useAuth()
  const canManage = can("manage_budgets")

  const [budgets, setBudgets] = useState<Budget[]>([])
  const [summary, setSummary] = useState<BudgetSummary | null>(null)
  const [countries, setCountries] = useState<CountrySummary[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Budget | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [budgetPage, summaryData, countryPage, projectPage] = await Promise.all([
        fetchBudgets({ page_size: 200 }),
        fetchBudgetSummary(),
        fetchCountries({ page_size: 200 }),
        fetchProjects({ page_size: 200 }),
      ])
      setBudgets(budgetPage.results)
      setSummary(summaryData)
      setCountries(countryPage.results)
      setProjects(projectPage.results)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger les budgets")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleSave = async (values: BudgetFormValues) => {
    if (editing) {
      await updateBudget(editing.id, values)
    } else {
      await createBudget(values)
    }
    setEditing(null)
    await load()
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Budgets</h1>
          <p className="text-sm text-muted-foreground">
            Enveloppes annuelles par pays, sous-enveloppes par projet et
            réallocations.
          </p>
        </div>
        {canManage && (
          <Button
            onClick={() => {
              setEditing(null)
              setFormOpen(true)
            }}
          >
            <Plus className="mr-2 h-4 w-4" />
            Attribuer une enveloppe
          </Button>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

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
          label="Disponible consolidé"
          value={formatAmount(summary?.total_remaining_xof, "FCFA")}
          hint="Converti au taux en vigueur"
        />
        <StatCard label="Pays dotés" value={String(summary?.countries.length ?? 0)} />
        <StatCard label="Enveloppes" value={String(budgets.length)} />
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
              <div className="overflow-hidden rounded-lg border border-border/60">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Pays</TableHead>
                      <TableHead className="text-right">Enveloppe</TableHead>
                      <TableHead className="text-right">Consommé</TableHead>
                      <TableHead className="text-right">Disponible</TableHead>
                      <TableHead className="text-right">Disponible (FCFA)</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={5} className="h-16">
                          <div className="h-4 animate-pulse rounded bg-muted" />
                        </TableCell>
                      </TableRow>
                    ) : !summary || summary.countries.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={5}
                          className="h-24 text-center text-muted-foreground"
                        >
                          Aucune enveloppe attribuée.
                        </TableCell>
                      </TableRow>
                    ) : (
                      summary.countries.map((row) => (
                        <TableRow key={row.country}>
                          <TableCell>
                            <p className="font-medium">{row.country_name}</p>
                            <p className="text-xs text-muted-foreground">
                              {row.country_ref ?? "—"} · {row.currency}
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
                            {formatAmount(row.consumed)}
                          </TableCell>
                          <TableCell className="text-right font-medium">
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
              <div className="overflow-hidden rounded-lg border border-border/60">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Enveloppe</TableHead>
                      <TableHead>Année</TableHead>
                      <TableHead className="text-right">Montant</TableHead>
                      <TableHead className="text-right">Disponible</TableHead>
                      <TableHead>Exécution</TableHead>
                      <TableHead>Dépassement</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {budgets.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={7}
                          className="h-24 text-center text-muted-foreground"
                        >
                          Aucune enveloppe.
                        </TableCell>
                      </TableRow>
                    ) : (
                      budgets.map((budget) => (
                        <TableRow key={budget.id}>
                          <TableCell>
                            <p className="font-medium">{budget.country_name}</p>
                            <p className="text-xs text-muted-foreground">
                              {budget.project_name ?? "Enveloppe du pays"}
                            </p>
                          </TableCell>
                          <TableCell>{budget.year}</TableCell>
                          <TableCell className="text-right">
                            {formatAmount(budget.amount, budget.currency)}
                          </TableCell>
                          <TableCell className="text-right font-medium">
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
                          <TableCell className="text-right">
                            {canManage && (
                              <Button
                                variant="ghost"
                                size="icon"
                                aria-label="Modifier"
                                onClick={() => {
                                  setEditing(budget)
                                  setFormOpen(true)
                                }}
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                            )}
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

        <TabsContent value="reallocations" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <Reallocations
                budgets={budgets}
                canDecide={canManage}
                onChanged={load}
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
        countries={countries}
        projects={projects}
        editing={editing}
      />
    </div>
  )
}

function StatCard({
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
          <Wallet className="h-3.5 w-3.5" />
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
