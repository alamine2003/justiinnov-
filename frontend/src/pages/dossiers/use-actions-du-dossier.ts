import { useState } from "react"
import { useTranslation } from "react-i18next"
import type { TransitionPayload } from "@/components/expenses/workflow-actions"
import {
  deleteExpenseDraft,
  renameDossier,
  reopenDossier,
  requestRectification,
  transitionDossier,
  transitionExpense,
} from "@/lib/expenses"
import type {
  DossierDetail,
  Expense,
  ExpenseTransitionName,
  Paginated,
  Rectification,
  TransitionName,
} from "@/lib/types"
import type { QueryResult } from "@/lib/use-query"
import { messageDErreur } from "@/lib/use-enregistrement"

/**
 * Ce que la fiche d'un dossier fait sur le serveur — transitions du dossier
 * et des lignes, réouverture, renommage, rectification, retrait d'un
 * brouillon ou d'une ligne mise à la corbeille — et les messages qui en
 * résultent en tête de page : l'erreur d'une action, l'avertissement
 * budgétaire du serveur, l'avis d'une mise à la corbeille.
 *
 * Avant chaque action, les messages de la précédente s'effacent
 * (`effacerLesMessages`), puis la fiche se met à jour : sur place quand le
 * serveur renvoie l'objet, par une relecture sinon. La fiche, elle, ne fait
 * plus qu'afficher (écart 23 de la revue d'architecture).
 */
export function useActionsDuDossier({
  dossierId,
  dossier,
  query,
  rectifications,
}: {
  dossierId: number
  dossier: DossierDetail | null
  query: QueryResult<DossierDetail>
  rectifications: QueryResult<Paginated<Rectification>>
}) {
  const { t } = useTranslation()
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  /** Ce que le super administrateur vient de mettre à la corbeille. */
  const [retiree, setRetiree] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const effacerLesMessages = () => {
    setActionError(null)
    setNotice(null)
    setRetiree(null)
  }

  /** La ligne quitte l'écran tout de suite ; le dossier est relu derrière. */
  const retirerDeLEcran = (expenseId: number) => {
    query.setData((current) =>
      current
        ? { ...current, expenses: current.expenses.filter((e) => e.id !== expenseId) }
        : current,
    )
    query.reload()
  }

  // Un refus est relancé aux boutons d'action : le dialogue l'affiche sans
  // se fermer, et une action directe le remet à la page (`onError`). Il
  // n'est donc jamais montré deux fois.
  const runExpenseTransition = async (
    expense: Expense,
    action: ExpenseTransitionName,
    payload?: TransitionPayload,
  ) => {
    effacerLesMessages()
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
    effacerLesMessages()
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
    effacerLesMessages()
    await reopenDossier(dossier.id, note)
    query.reload()
  }

  // Le renommage ne touche qu'au titre (décision 104) : la fiche renvoyée
  // remplace l'écran, le dialogue affiche lui-même un refus.
  const rename = async (label: string) => {
    effacerLesMessages()
    query.setData(await renameDossier(dossierId, label))
  }

  // La rectification n'est pas une transition : la ligne ne bouge qu'à la
  // décision d'un administrateur. Le dialogue affiche lui-même les refus
  // par champ, d'où l'erreur relancée ; la fiche est relue au succès
  // (`allowed_actions` de la ligne change : plus de nouvelle demande).
  const requestLineRectification = async (expense: Expense, motif: string) => {
    effacerLesMessages()
    await requestRectification(expense.id, motif)
    query.reload()
    rectifications.reload()
  }

  const afterRectificationDecided = async () => {
    effacerLesMessages()
    query.reload()
    rectifications.reload()
  }

  // Le retrait d'un brouillon n'efface que l'erreur : l'avertissement et
  // l'avis de corbeille d'avant restent lisibles.
  const removeDraft = async (expense: Expense) => {
    setDeletingId(expense.id)
    setActionError(null)
    try {
      await deleteExpenseDraft(expense.id)
      retirerDeLEcran(expense.id)
    } catch (e) {
      setActionError(messageDErreur(e, t("dossiers.detail.suppression_impossible")))
    } finally {
      setDeletingId(null)
    }
  }

  // Une ligne mise à la corbeille part tout de suite, comme au retrait d'un
  // brouillon ; ses demandes de rectification sont parties avec elle
  // (décision 120).
  const ligneALaCorbeille = (ligne: Expense) => {
    setActionError(null)
    setRetiree(t("corbeille.fait", { libelle: ligne.title }))
    retirerDeLEcran(ligne.id)
    rectifications.reload()
  }

  return {
    actionError,
    setActionError,
    notice,
    retiree,
    deletingId,
    effacerLesMessages,
    runExpenseTransition,
    runDossierTransition,
    reopen,
    rename,
    requestLineRectification,
    afterRectificationDecided,
    removeDraft,
    ligneALaCorbeille,
  }
}
