import { useState } from "react"
import { useParams } from "react-router-dom"
import { AlertTriangle, FileText, Loader2, Plus, RotateCcw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader } from "@/components/ui/page-header"
import { StatCard } from "@/components/ui/stat-card"
import { BarreEcart } from "@/components/ui/charts"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { CarteDeLigne } from "@/components/expenses/expense-line-card"
import { ExpenseForm } from "@/components/expenses/expense-form"
import { ProofPanel } from "@/components/expenses/proof-panel"
import { RectificationPanel } from "@/components/expenses/rectification-panel"
import { ReopenDossier } from "@/components/expenses/reopen-dossier"
import { StatusBadge } from "@/components/expenses/status-badge"
import { WorkflowActions, type TransitionPayload } from "@/components/expenses/workflow-actions"
import { FriseDuCircuit } from "@/components/expenses/workflow-frieze"
import { useAuth } from "@/context/use-auth"
import {
  createExpense,
  deleteExpenseDraft,
  fetchBeneficiaries,
  fetchDossier,
  fetchRectifications,
  reopenDossier,
  requestRectification,
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
import { formatAmount, formatDay } from "@/lib/utils"

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

  // Les demandes de rectification du dossier : une par ligne au plus en
  // attente, les tranchées restent lisibles. Relues avec le dossier après
  // une demande ou une décision, puisque les deux changent la ligne.
  const rectifications = useQuery(
    `rectifications:${dossierId}`,
    (signal) => fetchRectifications({ expense__dossier: dossierId, page_size: 100 }, signal),
  )

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

  // La rectification n'est pas une transition : la ligne ne bouge qu'à la
  // décision d'un administrateur. Le dialogue affiche lui-même les refus
  // par champ, d'où l'erreur relancée ; la fiche est relue au succès
  // (`allowed_actions` de la ligne change : plus de nouvelle demande).
  const requestLineRectification = async (expense: Expense, motif: string) => {
    setActionError(null)
    setNotice(null)
    await requestRectification(expense.id, motif)
    query.reload()
    rectifications.reload()
  }

  const afterRectificationDecided = async () => {
    setActionError(null)
    setNotice(null)
    query.reload()
    rectifications.reload()
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
      {rectifications.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("depenses.rectification.chargement_impossible")}</AlertTitle>
          <AlertDescription>{rectifications.error}</AlertDescription>
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

      {/* Le circuit en frise : où en est le dossier, avant tout chiffre. */}
      <Card className="border-border/60 shadow-sm">
        <CardContent className="overflow-x-auto pt-6">
          <FriseDuCircuit status={dossier.status} />
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label={t("dossiers.detail.stat_depenses")}
          value={formatAmount(dossier.totals.amount, currencySymbol)}
        />
        <StatCard
          label={t("champs.justified_amount")}
          value={formatAmount(dossier.totals.justified, currencySymbol)}
        >
          <BarreEcart
            className="mt-3 h-1.5"
            amount={Number(dossier.totals.amount)}
            justified={Number(dossier.totals.justified)}
            title={t("dossiers.detail.barre_dossier_aria", {
              justifie: formatAmount(dossier.totals.justified),
              depense: formatAmount(dossier.totals.amount),
            })}
          />
        </StatCard>
        <StatCard
          label={t("dossiers.detail.stat_ecart")}
          value={formatAmount(dossier.totals.gap, currencySymbol)}
          tone={Number(dossier.totals.gap) > 0 ? "danger" : undefined}
          hint={Number(dossier.totals.gap) > 0 ? t("dossiers.detail.ecart_aide") : undefined}
        />
      </div>

      {/* Les lignes à gauche, les preuves et les rectifications dans un rail
          à droite : on justifie une ligne en regardant la pièce. */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_21rem] xl:items-start">
        <Card className="border-border/60 shadow-sm">
          <CardContent className="space-y-3 pt-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold">
                  {t("dossiers.detail.lignes_compte", { count: dossier.expenses.length })}
                </h3>
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

            {dossier.expenses.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border/60 p-8 text-center">
                <FileText className="mx-auto h-5 w-5 text-muted-foreground" aria-hidden />
                <p className="mt-2 text-sm font-medium">{t("dossiers.detail.vide.titre")}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {canAddLine
                    ? t("dossiers.detail.vide.aide_ajouter")
                    : t("dossiers.detail.vide.aide_verrouille")}
                </p>
              </div>
            ) : (
              <ul className="space-y-2.5">
                {dossier.expenses.map((expense) => (
                  <CarteDeLigne
                    key={expense.id}
                    expense={expense}
                    currency={currencySymbol}
                    deleting={deletingId === expense.id}
                    onEdit={(ligne) => {
                      setEditing(ligne)
                      setFormOpen(true)
                    }}
                    onDelete={(ligne) => void removeDraft(ligne)}
                    onTransition={runExpenseTransition}
                    onRequestRectification={requestLineRectification}
                    onError={setActionError}
                  />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
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

          {(rectifications.data?.results.length ?? 0) > 0 && (
            <Card className="border-border/60 shadow-sm">
              <CardContent className="pt-6">
                <RectificationPanel
                  rows={rectifications.data?.results ?? []}
                  currency={currencySymbol}
                  onDecided={afterRectificationDecided}
                />
              </CardContent>
            </Card>
          )}
        </div>
      </div>

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
        defaultOwner={dossier.owner}
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
