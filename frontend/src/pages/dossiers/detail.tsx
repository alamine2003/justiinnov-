import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { AlertTriangle, ArrowLeft, FileText, Loader2, Pencil, Plus, Trash2 } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
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
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { ExpenseForm } from "@/components/expenses/expense-form"
import { ProofPanel } from "@/components/expenses/proof-panel"
import { OriginalAmount } from "@/components/expenses/original-amount"
import { StatusBadge } from "@/components/expenses/status-badge"
import { WorkflowActions, type TransitionPayload } from "@/components/expenses/workflow-actions"
import { useAuth } from "@/context/use-auth"
import {
  createExpense,
  deleteExpenseDraft,
  fetchBeneficiaries,
  fetchDossier,
  transitionDossier,
  transitionExpense,
  updateExpense,
} from "@/lib/expenses"
import { fetchCountry } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import {
  DELETABLE_STATUSES,
  LOCKED_STATUSES,
  type Expense,
  type TransitionName,
} from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn, formatAmount, formatDateIn, formatDay } from "@/lib/utils"

export function DossierDetailPage() {
  const { id } = useParams<{ id: string }>()
  const dossierId = Number(id)
  const { can } = useAuth()
  const canWrite = can("record_expenses")

  const query = useQuery(
    `dossier:${dossierId}`,
    (signal) => fetchDossier(dossierId, signal),
    { fallback: "Impossible de charger le dossier" },
  )
  const dossier = query.data
  const countryId = dossier?.country

  // Le référentiel du pays vient de sa fiche, mise en cache : une transition
  // ne recharge que le dossier, pas les équipes et projets.
  const country = useReferentiel(
    `country:${countryId}`,
    () => fetchCountry(Number(countryId)),
    { enabled: countryId !== undefined },
  )
  const beneficiaries = useReferentiel(
    `beneficiaries:${countryId}`,
    () => fetchBeneficiaries({ country: countryId, page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: countryId !== undefined },
  )

  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Expense | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const runExpenseTransition = async (
    expense: Expense,
    action: TransitionName,
    payload?: TransitionPayload,
  ) => {
    setActionError(null)
    setNotice(null)
    try {
      const result = await transitionExpense(expense.id, action, payload)
      if (result.warning) setNotice(result.warning)
      // La ligne est remplacée sur place ; le dossier (totaux, statut) est
      // relu en arrière-plan, sans repasser par l'écran de chargement.
      query.setData((current) =>
        current
          ? {
              ...current,
              expenses: current.expenses.map((e) => (e.id === expense.id ? { ...e, ...result } : e)),
            }
          : current,
      )
      query.reload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Action impossible")
      throw e
    }
  }

  const runDossierTransition = async (action: TransitionName, payload?: TransitionPayload) => {
    if (!dossier) return
    setActionError(null)
    setNotice(null)
    try {
      const result = await transitionDossier(dossier.id, action, payload)
      if (result.warning) setNotice(result.warning)
      query.reload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Action impossible")
      throw e
    }
  }

  const removeDraft = async (expense: Expense) => {
    setDeletingId(expense.id)
    setActionError(null)
    try {
      await deleteExpenseDraft(expense.id)
      query.setData((current) =>
        current
          ? { ...current, expenses: current.expenses.filter((e) => e.id !== expense.id) }
          : current,
      )
      query.reload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Suppression impossible")
    } finally {
      setDeletingId(null)
    }
  }

  if (query.loading && !dossier) {
    return (
      <div className="flex h-64 items-center justify-center" aria-busy="true">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="sr-only">Chargement du dossier…</span>
      </div>
    )
  }

  if (!dossier) {
    return (
      <div className="space-y-4">
        <BackLink />
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Dossier introuvable</AlertTitle>
          <AlertDescription>{query.error ?? "Ce dossier n'existe pas ou n'est pas dans votre périmètre."}</AlertDescription>
        </Alert>
      </div>
    )
  }

  const locked = LOCKED_STATUSES.includes(dossier.status)
  const currencySymbol = country.data?.currency_symbol || dossier.currency
  const teams = (country.data?.teams ?? []).filter((t) => t.is_active)
  const projects = (country.data?.projects ?? []).filter((p) => p.is_active)
  const expenseTitles = (country.data?.expense_titles ?? []).filter((t) => t.is_active)
  const marketingCategories = (country.data?.marketing_categories ?? []).filter((c) => c.is_active)
  const managers = (country.data?.managers ?? []).filter((m) => m.is_active)

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
    query.reload()
  }

  return (
    <div className="space-y-6">
      <BackLink />

      {(query.error || actionError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{actionError ?? query.error}</AlertDescription>
        </Alert>
      )}
      {country.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Référentiel du pays indisponible</AlertTitle>
          <AlertDescription>{country.error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Avertissement budgétaire</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={beneficiaries.data} noun="bénéficiaires" />

      <PageHeader
        title={dossier.number}
        description={
          <>
            <span className="mr-2 inline-flex align-middle">
              <StatusBadge status={dossier.status} label={dossier.status_display} />
            </span>
            {dossier.label} · {dossier.country_ref ?? dossier.country_name} ·{" "}
            {formatDay(dossier.date)}
            {dossier.team_name && ` · ${dossier.team_name}`}
            {dossier.owner_name && ` · ${dossier.owner_name}`}
            {dossier.created_by && ` · créé par ${dossier.created_by}`}
            {query.refreshing && (
              <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin align-middle" aria-label="Actualisation" />
            )}
            {dossier.note && (
              <span className="mt-1 block italic">Contrôle : {dossier.note}</span>
            )}
          </>
        }
      >
        <WorkflowActions
          status={dossier.status}
          subject="dossier"
          onTransition={runDossierTransition}
        />
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Dépenses" value={formatAmount(dossier.totals.amount, currencySymbol)} />
        <StatCard label="Montant justifié" value={formatAmount(dossier.totals.justified, currencySymbol)} />
        <StatCard
          label="Écart"
          value={formatAmount(dossier.totals.gap, currencySymbol)}
          hint={Number(dossier.totals.gap) > 0 ? "Dépensé sans preuve à l'appui" : undefined}
        />
      </div>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="space-y-3 pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold">Lignes de dépenses</h3>
              <p className="text-xs text-muted-foreground">
                Chaque ligne suit son propre circuit de justification.
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
                <Plus className="mr-1 h-4 w-4" aria-hidden />
                Ajouter
              </Button>
            )}
          </div>

          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Libellé</TableHead>
                  <TableHead scope="col">Date</TableHead>
                  <TableHead scope="col" className="text-right">Dépense</TableHead>
                  <TableHead scope="col" className="text-right">Justifié</TableHead>
                  <TableHead scope="col" className="text-right">Écart</TableHead>
                  <TableHead scope="col">Statut</TableHead>
                  <TableHead scope="col" className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dossier.expenses.length === 0 ? (
                  <EmptyRow
                    colSpan={7}
                    icon={FileText}
                    title="Aucune ligne"
                    hint={
                      canWrite && !locked
                        ? "Ajoutez les dépenses de ce dossier avant de le soumettre."
                        : "Ce dossier ne contient aucune dépense."
                    }
                  />
                ) : (
                  dossier.expenses.map((expense) => (
                    <TableRow key={expense.id}>
                      <TableCell>
                        <p className="font-medium">{expense.title}</p>
                        <p className="text-xs text-muted-foreground">
                          {expense.place || "—"}
                          {expense.budget_label && ` · imputé sur ${expense.budget_label}`}
                          {expense.created_by && ` · saisie par ${expense.created_by}`}
                        </p>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateIn(expense.date, expense.country_timezone)}
                        <br />
                        <span className="opacity-70">
                          heure {expense.country_timezone}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(expense.amount)}
                        <OriginalAmount
                          currency={expense.original_currency}
                          amount={expense.original_amount}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        {formatAmount(expense.justified_amount)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right font-medium",
                          Number(expense.gap) > 0 && "text-destructive",
                        )}
                      >
                        {formatAmount(expense.gap)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={expense.status} label={expense.status_display} />
                        {expense.control_note && (
                          <p className="mt-1 max-w-[14rem] text-xs italic text-muted-foreground">
                            Contrôle : {expense.control_note}
                          </p>
                        )}
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
                              aria-label={`Modifier ${expense.title}`}
                              onClick={() => {
                                setEditing(expense)
                                setFormOpen(true)
                              }}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          )}
                          {canWrite && DELETABLE_STATUSES.includes(expense.status) && (
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Supprimer le brouillon ${expense.title}`}
                              className="text-destructive hover:text-destructive"
                              disabled={deletingId === expense.id}
                              onClick={() => void removeDraft(expense)}
                            >
                              {deletingId === expense.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4" />
                              )}
                            </Button>
                          )}
                          <WorkflowActions
                            status={expense.status}
                            amount={expense.amount}
                            currency={currencySymbol}
                            // Le dossier emporte ses lignes : tant qu'il est
                            // en brouillon, c'est lui qu'on soumet.
                            hideSubmit={dossier.status === "draft"}
                            onTransition={(action, payload) =>
                              runExpenseTransition(expense, action, payload)
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
            onChanged={async () => {
              query.reload()
            }}
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
        beneficiaries={beneficiaries.data?.results ?? []}
        expenseTitles={expenseTitles}
        marketingCategories={marketingCategories}
        managers={managers}
        currency={currencySymbol}
        timezone={dossier.country_timezone}
      />
    </div>
  )
}

function BackLink() {
  return (
    <Link
      to="/dossiers"
      className="inline-flex items-center rounded text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowLeft className="mr-2 h-4 w-4" aria-hidden />
      Retour aux dossiers
    </Link>
  )
}
