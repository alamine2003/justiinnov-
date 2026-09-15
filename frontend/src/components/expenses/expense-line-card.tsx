import { Loader2, Pencil, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { BarreEcart } from "@/components/ui/charts"
import { OriginalAmount } from "@/components/expenses/original-amount"
import { RequestRectification } from "@/components/expenses/request-rectification"
import { StatusBadge } from "@/components/expenses/status-badge"
import { WorkflowActions, type TransitionPayload } from "@/components/expenses/workflow-actions"
import type { Expense, ExpenseTransitionName } from "@/lib/types"
import { cn, formatAmount, formatDateIn } from "@/lib/utils"

/**
 * Une ligne de dépense en carte : le montant à droite, la barre justifié /
 * écart dessous, les actions du circuit en pied. Le tableau d'avant obligeait
 * à lire sept colonnes pour savoir si une dépense avait sa preuve ; ici la
 * barre le dit avant les chiffres.
 *
 * Ce qui est possible sur la ligne vient de `allowed_actions` : la carte
 * n'a aucune liste d'états ni de rôles.
 */
export function CarteDeLigne({
  expense,
  currency,
  deleting,
  onEdit,
  onDelete,
  onTransition,
  onRequestRectification,
  onError,
}: {
  expense: Expense
  currency: string
  deleting: boolean
  onEdit: (expense: Expense) => void
  onDelete: (expense: Expense) => void
  onTransition: (
    expense: Expense,
    action: ExpenseTransitionName,
    payload?: TransitionPayload,
  ) => Promise<void>
  onRequestRectification: (expense: Expense, motif: string) => Promise<void>
  onError: (message: string | null) => void
}) {
  const { t } = useTranslation()
  const montant = Number(expense.amount)
  const justifie = Number(expense.justified_amount)
  const ecart = Number(expense.gap)
  // Un brouillon n'a rien à montrer : il n'est pas encore déclaré, et une
  // barre vide qui se lirait « tout en écart » serait un contresens.
  const declaree = expense.status !== "draft"

  const contexte = [
    formatDateIn(expense.date, expense.country_timezone),
    t("dossiers.detail.heure_fuseau", { fuseau: expense.country_timezone }),
    expense.place || null,
    expense.payment_method_display,
    expense.beneficiary_name,
    expense.budget_label &&
      t("dossiers.detail.impute_sur", { budget: expense.budget_label }),
    expense.created_by && t("dossiers.detail.saisie_par", { nom: expense.created_by }),
  ].filter(Boolean)

  const note = expense.control_note
    ? t("dossiers.detail.note_controle", { note: expense.control_note })
    : expense.note

  return (
    <li
      className={cn(
        "rounded-lg border p-3.5",
        expense.status === "in_review"
          ? "border-statut-attente/40 bg-statut-attente/5"
          : expense.status === "unjustified"
            ? "border-destructive/30 bg-destructive/5"
            : "border-border/60",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold">{expense.title}</h4>
            <StatusBadge status={expense.status} label={expense.status_display} />
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {contexte.join(" · ")}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-base font-semibold tracking-tight">
            {declaree ? formatAmount(expense.amount, currency) : "—"}
          </p>
          <OriginalAmount
            currency={expense.original_currency}
            amount={expense.original_amount}
          />
          <p className="mt-0.5 text-xs text-muted-foreground">
            {declaree
              ? t("dossiers.detail.justifie_de", { montant: formatAmount(expense.justified_amount) })
              : t("dossiers.detail.non_soumise")}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-3">
        {declaree ? (
          <BarreEcart
            amount={montant}
            justified={justifie}
            title={t("dossiers.detail.barre_aria", {
              titre: expense.title,
              justifie: formatAmount(expense.justified_amount),
              depense: formatAmount(expense.amount),
            })}
          />
        ) : (
          <div aria-hidden className="h-2 flex-1 rounded-full bg-muted" />
        )}
        <span
          className={cn(
            "shrink-0 text-xs font-medium",
            !declaree
              ? "text-muted-foreground"
              : ecart > 0
                ? "text-destructive"
                : "text-marque-fort",
          )}
        >
          {!declaree
            ? t("dossiers.detail.attente_soumission")
            : ecart > 0
              ? t("dossiers.detail.ecart_de", { montant: formatAmount(expense.gap) })
              : t("dossiers.detail.ecart_nul")}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-3">
        <p className="min-w-0 flex-1 text-xs italic text-muted-foreground">{note}</p>
        <div className="flex shrink-0 items-center gap-1">
          {expense.allowed_actions.includes("edit") && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("dossiers.detail.modifier_aria", { titre: expense.title })}
              onClick={() => onEdit(expense)}
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
              disabled={deleting}
              onClick={() => onDelete(expense)}
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </Button>
          )}
          <WorkflowActions
            amount={expense.amount}
            currency={currency}
            allowedActions={expense.allowed_actions}
            onTransition={(action, payload) => onTransition(expense, action, payload)}
            onError={onError}
          />
          <RequestRectification
            expense={expense}
            onRequest={(motif) => onRequestRectification(expense, motif)}
          />
        </div>
      </div>
    </li>
  )
}
