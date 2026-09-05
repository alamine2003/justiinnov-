import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import {
  AlertTriangle,
  ArrowLeft,
  FileText,
  Loader2,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
} from "lucide-react"
import { useTranslation } from "react-i18next"
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
import { ReopenDossier } from "@/components/expenses/reopen-dossier"
import { StatusBadge } from "@/components/expenses/status-badge"
import { WorkflowActions, type TransitionPayload } from "@/components/expenses/workflow-actions"
import { useAuth } from "@/context/use-auth"
import {
  createExpense,
  deleteExpenseDraft,
  fetchBeneficiaries,
  fetchDossier,
  reopenDossier,
  transitionDossier,
  transitionExpense,
  updateExpense,
} from "@/lib/expenses"
import { fetchCountry } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import { scopedTeams, teamRequired } from "@/lib/teams"
import {
  type Expense,
  type ExpenseTransitionName,
  type TransitionName,
} from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn, formatAmount, formatDateIn, formatDay } from "@/lib/utils"

export function DossierDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const dossierId = Number(id)
  const { me } = useAuth()

  const query = useQuery(
    `dossier:${dossierId}`,
    (signal) => fetchDossier(dossierId, signal),
    { fallback: t("dossiers.detail.chargement_impossible") },
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

  // Un refus est relancé aux boutons d'action : le dialogue l'affiche sans
  // se fermer, et une action directe le remet à la page (`onError`). Il
  // n'est donc jamais montré deux fois.
  const runExpenseTransition = async (
    expense: Expense,
    action: ExpenseTransitionName,
    payload?: TransitionPayload,
  ) => {
    setActionError(null)
    setNotice(null)
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
  }

  const runDossierTransition = async (action: TransitionName, payload?: TransitionPayload) => {
    if (!dossier) return
    setActionError(null)
    setNotice(null)
    const { warning, ...result } = await transitionDossier(dossier.id, action, payload)
    if (warning) setNotice(warning)
    // La transition renvoie le détail complet : il remplace l'écran sans
    // attendre la relecture, qui confirme en arrière-plan.
    query.setData(result)
    query.reload()
  }

  // La réouverture n'est pas une transition du circuit : elle a sa propre
  // route et son propre droit. Le dialogue affiche lui-même les refus par
  // champ, d'où l'erreur relancée ; la fiche est relue au succès.
  const reopen = async (note: string) => {
    if (!dossier) return
    setActionError(null)
    setNotice(null)
    await reopenDossier(dossier.id, note)
    query.reload()
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
      setActionError(e instanceof Error ? e.message : t("dossiers.detail.suppression_impossible"))
    } finally {
      setDeletingId(null)
    }
  }

  if (query.loading && !dossier) {
    return (
      <div className="flex h-64 items-center justify-center" aria-busy="true">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="sr-only">{t("dossiers.detail.chargement")}</span>
      </div>
    )
  }

  if (!dossier) {
    return (
      <div className="space-y-4">
        <BackLink />
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("dossiers.detail.introuvable_titre")}</AlertTitle>
          <AlertDescription>
            {query.error ?? t("dossiers.detail.introuvable_texte")}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  // Ce qui se saisit encore vient du serveur (`allowed_actions`) : brouillon
  // ou non, droit ou non, l'interface ne recopie aucune règle. Une pièce se
  // dépose jusqu'à la clôture : une preuve arrivée après coup peut encore
  // justifier ce qui ne l'était pas.
  const canAddLine = dossier.allowed_actions.includes("add_line")
  const canUpload = dossier.allowed_actions.includes("upload")
  // Un libellé, pas une règle : le panneau des pièces explique pourquoi le
  // dépôt est fermé ; le droit de déposer, lui, vient de `allowed_actions`.
  const closed = dossier.status === "closed"
  const currencySymbol = country.data?.currency_symbol || dossier.currency
  // Un manager rattaché à des équipes ne saisit que pour elles ; l'équipe du
  // dossier, elle, figure toujours, puisque chaque ligne la porte.
  const teams = (country.data?.teams ?? []).filter(
    (equipe) =>
      equipe.id === dossier.team ||
      (equipe.is_active && scopedTeams([equipe], me).length > 0),
  )
  const projects = (country.data?.projects ?? []).filter((p) => p.is_active)
  const expenseTitles = (country.data?.expense_titles ?? []).filter((titre) => titre.is_active)
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
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{actionError ?? query.error}</AlertDescription>
        </Alert>
      )}
      {country.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("dossiers.detail.referentiel_indisponible")}</AlertTitle>
          <AlertDescription>{country.error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("dossiers.detail.avertissement_budgetaire")}</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}
      {/* Rouvert par le siège : le motif reste affiché tant que le dossier
          n'a pas été soumis à nouveau. */}
      {dossier.reopen_note && dossier.status === "draft" && (
        <Alert>
          <RotateCcw className="h-4 w-4" />
          <AlertTitle>{t("dossiers.reouverture.bandeau_titre")}</AlertTitle>
          <AlertDescription>
            {t("dossiers.reouverture.bandeau_motif", { motif: dossier.reopen_note })}
          </AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={beneficiaries.data} noun={t("dossiers.noms_beneficiaires")} />

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
            {dossier.created_by &&
              ` · ${t("dossiers.detail.cree_par", { nom: dossier.created_by })}`}
            {query.refreshing && (
              <Loader2
                className="ml-2 inline h-3.5 w-3.5 animate-spin align-middle"
                aria-label={t("dossiers.detail.actualisation")}
              />
            )}
            {dossier.note && (
              <span className="mt-1 block italic">
                {t("dossiers.detail.note_controle", { note: dossier.note })}
              </span>
            )}
          </>
        }
      >
        <WorkflowActions
          subject="dossier"
          allowedActions={dossier.allowed_actions}
          onTransition={runDossierTransition}
          onError={setActionError}
        />
        <ReopenDossier dossier={dossier} onReopen={reopen} />
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label={t("dossiers.detail.stat_depenses")}
          value={formatAmount(dossier.totals.amount, currencySymbol)}
        />
        <StatCard
          label={t("champs.justified_amount")}
          value={formatAmount(dossier.totals.justified, currencySymbol)}
        />
        <StatCard
          label={t("dossiers.detail.stat_ecart")}
          value={formatAmount(dossier.totals.gap, currencySymbol)}
          hint={Number(dossier.totals.gap) > 0 ? t("dossiers.detail.ecart_aide") : undefined}
        />
      </div>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="space-y-3 pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold">{t("dossiers.detail.lignes_titre")}</h3>
              <p className="text-xs text-muted-foreground">
                {t("dossiers.detail.lignes_description")}
              </p>
            </div>
            {canAddLine && (
              <Button
                size="sm"
                onClick={() => {
                  setEditing(null)
                  setFormOpen(true)
                }}
              >
                <Plus className="mr-1 h-4 w-4" aria-hidden />
                {t("commun.ajouter")}
              </Button>
            )}
          </div>

          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">{t("champs.label")}</TableHead>
                  <TableHead scope="col">{t("commun.date")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("dossiers.detail.colonnes.depense")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("dossiers.detail.colonnes.justifie")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("dossiers.detail.colonnes.ecart")}</TableHead>
                  <TableHead scope="col">{t("commun.statut")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("commun.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dossier.expenses.length === 0 ? (
                  <EmptyRow
                    colSpan={7}
                    icon={FileText}
                    title={t("dossiers.detail.vide.titre")}
                    hint={
                      canAddLine
                        ? t("dossiers.detail.vide.aide_ajouter")
                        : t("dossiers.detail.vide.aide_verrouille")
                    }
                  />
                ) : (
                  dossier.expenses.map((expense) => (
                    <TableRow key={expense.id}>
                      <TableCell>
                        <p className="font-medium">{expense.title}</p>
                        <p className="text-xs text-muted-foreground">
                          {expense.place || t("commun.aucun")}
                          {expense.budget_label &&
                            ` · ${t("dossiers.detail.impute_sur", { budget: expense.budget_label })}`}
                          {expense.created_by &&
                            ` · ${t("dossiers.detail.saisie_par", { nom: expense.created_by })}`}
                        </p>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateIn(expense.date, expense.country_timezone)}
                        <br />
                        <span className="opacity-70">
                          {t("dossiers.detail.heure_fuseau", { fuseau: expense.country_timezone })}
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
                            {t("dossiers.detail.note_controle", { note: expense.control_note })}
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
                          {expense.allowed_actions.includes("edit") && (
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={t("dossiers.detail.modifier_aria", { titre: expense.title })}
                              onClick={() => {
                                setEditing(expense)
                                setFormOpen(true)
                              }}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          )}
                          {expense.allowed_actions.includes("delete") && (
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={t("dossiers.detail.supprimer_aria", { titre: expense.title })}
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
                            amount={expense.amount}
                            currency={currencySymbol}
                            allowedActions={expense.allowed_actions}
                            onTransition={(action, payload) =>
                              runExpenseTransition(expense, action, payload)
                            }
                            onError={setActionError}
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
            canUpload={canUpload}
            closed={closed}
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
        teamRequired={teamRequired(me)}
        // Une ligne porte l'équipe de son dossier : le serveur refuse une
        // autre équipe.
        lockedTeam={dossier.team}
      />
    </div>
  )
}

function BackLink() {
  const { t } = useTranslation()
  return (
    <Link
      to="/dossiers"
      className="inline-flex items-center rounded text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowLeft className="mr-2 h-4 w-4" aria-hidden />
      {t("dossiers.detail.retour")}
    </Link>
  )
}
