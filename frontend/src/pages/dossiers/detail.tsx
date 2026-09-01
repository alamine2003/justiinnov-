import { useCallback, useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { AlertTriangle, ArrowLeft, Loader2, Pencil, Plus } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { ExpenseForm } from "@/components/expenses/expense-form"
import { ProofPanel } from "@/components/expenses/proof-panel"
import { StatusBadge } from "@/components/expenses/status-badge"
import { WorkflowActions } from "@/components/expenses/workflow-actions"
import { useAuth } from "@/context/auth"
import {
  createExpense,
  fetchBeneficiaries,
  fetchDossier,
  transitionDossier,
  transitionExpense,
  updateExpense,
} from "@/lib/expenses"
import { fetchProjects, fetchTeams } from "@/lib/countries"
import {
  LOCKED_STATUSES,
  type Beneficiary,
  type DossierDetail,
  type Expense,
  type Project,
  type Team,
  type TransitionName,
} from "@/lib/types"
import { formatAmount, formatDate } from "@/lib/utils"

export function DossierDetailPage() {
  const { id } = useParams<{ id: string }>()
  const dossierId = Number(id)
  const { can } = useAuth()
  const canWrite = can("record_expenses")

  const [dossier, setDossier] = useState<DossierDetail | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Expense | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDossier(dossierId)
      setDossier(data)
      const [teamPage, projectPage, beneficiaryPage] = await Promise.all([
        fetchTeams({ country: data.country, page_size: 200 }),
        fetchProjects({ country: data.country, page_size: 200 }),
        fetchBeneficiaries({ page_size: 200 }),
      ])
      setTeams(teamPage.results)
      setProjects(projectPage.results)
      setBeneficiaries(beneficiaryPage.results)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger le dossier")
    } finally {
      setLoading(false)
    }
  }, [dossierId])

  useEffect(() => {
    void load()
  }, [load])

  const runTransition = async (
    action: TransitionName,
    note: string | undefined,
    apply: (action: TransitionName, note?: string) => Promise<{ warning?: string }>,
  ) => {
    setError(null)
    setNotice(null)
    try {
      const result = await apply(action, note)
      if (result.warning) setNotice(result.warning)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action impossible")
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!dossier) {
    return (
      <div className="space-y-4">
        <BackLink />
        <p className="text-muted-foreground">{error ?? "Dossier introuvable."}</p>
      </div>
    )
  }

  const locked = LOCKED_STATUSES.includes(dossier.status)

  const saveExpense = async (values: Record<string, unknown>) => {
    if (editing) {
      await updateExpense(editing.id, values)
    } else {
      await createExpense({
        ...values,
        dossier: dossier.id,
        country: dossier.country,
      })
    }
    setEditing(null)
    await load()
  }

  return (
    <div className="space-y-6">
      <BackLink />

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Avertissement budgétaire</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{dossier.number}</h1>
            <StatusBadge status={dossier.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            {dossier.label} · {dossier.country_ref ?? dossier.country_name} ·{" "}
            {new Date(dossier.date).toLocaleDateString("fr-FR")}
            {dossier.team_name && ` · ${dossier.team_name}`}
          </p>
          {dossier.note && (
            <p className="mt-1 text-sm italic text-muted-foreground">
              Contrôle : {dossier.note}
            </p>
          )}
        </div>
        <WorkflowActions
          status={dossier.status}
          onTransition={(action, note) =>
            runTransition(action, note, (a, n) => transitionDossier(dossier.id, a, n))
          }
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Dépenses" value={formatAmount(dossier.totals.amount, dossier.currency)} />
        <StatCard label="Montant justifié" value={formatAmount(dossier.totals.justified)} />
        <StatCard label="Écart" value={formatAmount(dossier.totals.gap)} />
      </div>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="space-y-3 pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold">Lignes de dépenses</h3>
              <p className="text-xs text-muted-foreground">
                Chaque ligne suit son propre circuit de validation.
              </p>
            </div>
            {canWrite && !locked && (
              <Button
                size="sm"
                onClick={() => {
                  setEditing(null)
                  setFormOpen(true)
                }}
              >
                <Plus className="mr-1 h-4 w-4" />
                Ajouter
              </Button>
            )}
          </div>

          <div className="overflow-hidden rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Libellé</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead className="text-right">Dépense</TableHead>
                  <TableHead className="text-right">Justifié</TableHead>
                  <TableHead className="text-right">Écart</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dossier.expenses.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="h-16 text-center text-muted-foreground">
                      Aucune ligne.
                    </TableCell>
                  </TableRow>
                ) : (
                  dossier.expenses.map((expense) => (
                    <TableRow key={expense.id}>
                      <TableCell>
                        <p className="font-medium">{expense.title}</p>
                        <p className="text-xs text-muted-foreground">
                          {expense.place || "—"}
                          {expense.budget_label && ` · imputé sur ${expense.budget_label}`}
                        </p>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDate(expense.date)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(expense.amount)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(expense.justified_amount)}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {formatAmount(expense.gap)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={expense.status} />
                        {expense.note && (
                          <p className="mt-1 max-w-[14rem] text-xs italic text-muted-foreground">
                            {expense.note}
                          </p>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-1">
                          {canWrite && !LOCKED_STATUSES.includes(expense.status) && (
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label="Modifier"
                              onClick={() => {
                                setEditing(expense)
                                setFormOpen(true)
                              }}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          )}
                          <WorkflowActions
                            status={expense.status}
                            onTransition={(action, note) =>
                              runTransition(action, note, (a, n) =>
                                transitionExpense(expense.id, a, n),
                              )
                            }
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <ProofPanel
            dossierId={dossier.id}
            proofs={dossier.proofs}
            canUpload={canWrite && !locked}
            onChanged={load}
          />
        </CardContent>
      </Card>

      <ExpenseForm
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open)
          if (!open) setEditing(null)
        }}
        onSave={saveExpense}
        editing={editing}
        teams={teams}
        projects={projects}
        beneficiaries={beneficiaries}
        currency={dossier.currency}
      />
    </div>
  )
}

function BackLink() {
  return (
    <Link
      to="/dossiers"
      className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="mr-2 h-4 w-4" />
      Retour aux dossiers
    </Link>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold tracking-tight">{value}</p>
      </CardContent>
    </Card>
  )
}
