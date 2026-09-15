import { Pencil, Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Jauge, Legende, RailEnveloppe } from "@/components/ui/charts"
import { STATUS_TONES } from "@/lib/status-styles"
import type { Budget, CountryBudgetRow } from "@/lib/types"
import { cn, formatAmount, formatRate } from "@/lib/utils"

/**
 * L'enveloppe d'un pays sur toute la largeur, avec les seuils d'alerte de la
 * configuration gradués dessus. Le pointillé marque le montant justifié :
 * l'écart entre le remplissage et le pointillé, c'est ce qui manque de preuve.
 */
export function EnveloppeDuPays({
  row,
  budget,
  thresholds,
  symbol,
  onEdit,
}: {
  row: CountryBudgetRow
  /** L'enveloppe de portée « pays » de l'exercice, quand elle existe. */
  budget: Budget | undefined
  /** Seuils d'alerte en pourcentage ; sans configuration lisible, le seul plafond. */
  thresholds: number[]
  symbol: string
  onEdit?: (budget: Budget) => void
}) {
  const { t } = useTranslation()
  const allocated = Number(row.allocated)
  const depasse = Number(row.remaining) < 0

  return (
    <Card className="border-border/60 shadow-sm">
      <CardContent className="space-y-5 pt-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold">
              {t("budgets.enveloppe.titre", { pays: row.country_name })}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {[
                row.country_ref ?? t("commun.aucun"),
                t("budgets.enveloppe.exercice", { annee: budget?.year }),
                symbol,
                budget && t("budgets.enveloppe.depassement", {
                  politique: budget.overrun_policy_display,
                }),
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
          <div className="flex items-start gap-6">
            <div className="text-right">
              <p className="text-[0.5938rem] font-medium uppercase tracking-[0.07em] text-muted-foreground">
                {t("budgets.enveloppe.attribue")}
              </p>
              <p className="mt-1 text-lg font-semibold tracking-tight">
                {formatAmount(row.allocated)}
              </p>
            </div>
            <div className="text-right">
              <p className="text-[0.5938rem] font-medium uppercase tracking-[0.07em] text-muted-foreground">
                {t("budgets.colonnes.disponible")}
              </p>
              <p
                className={cn(
                  "mt-1 text-lg font-semibold tracking-tight",
                  depasse ? "text-destructive" : "text-marque-fort",
                )}
              >
                {formatAmount(row.remaining)}
              </p>
            </div>
            {budget && onEdit && (
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("budgets.modifier_aria", {
                  pays: row.country_name,
                  annee: budget.year,
                })}
                onClick={() => onEdit(budget)}
              >
                <Pencil className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        <RailEnveloppe
          consumed={Number(row.consumed)}
          engaged={Number(row.engaged)}
          justified={Number(row.justified)}
          allocated={allocated}
          thresholds={thresholds}
          thresholdLabels={thresholds.map((seuil) =>
            t("budgets.enveloppe.seuil", { seuil }),
          )}
          title={t("budgets.enveloppe.rail_aria", {
            pays: row.country_name,
            taux: formatRate(budget?.figures.execution_rate),
          })}
        />

        <Legende
          className="border-t border-border/60 pt-4"
          items={[
            {
              tone: "bg-marque",
              label: t("budgets.enveloppe.legende_consomme", {
                montant: formatAmount(row.consumed),
              }),
            },
            {
              tone: "bg-marque-clair",
              label: t("budgets.enveloppe.legende_engage", {
                montant: formatAmount(row.engaged),
              }),
            },
            {
              tone: "bg-muted",
              label: t("budgets.enveloppe.legende_disponible", {
                montant: formatAmount(row.remaining),
              }),
            },
            {
              tone: "border-marque-fort",
              dashed: true,
              label: t("budgets.enveloppe.legende_justifie", {
                montant: formatAmount(row.justified),
              }),
            },
          ]}
        />
      </CardContent>
    </Card>
  )
}

/**
 * Les sous-enveloppes du pays en jauges, et une carte en pointillé pour ce
 * qui n'est pas réparti — la seule façon de voir d'un coup d'œil qu'il reste
 * de l'enveloppe à découper.
 */
export function SousEnveloppes({
  budgets,
  row,
  warningRate,
  canCreate,
  canEdit,
  onCreate,
  onEdit,
}: {
  budgets: Budget[]
  row: CountryBudgetRow
  warningRate: number
  canCreate: boolean
  canEdit: boolean
  onCreate: () => void
  onEdit: (budget: Budget) => void
}) {
  const { t } = useTranslation()
  const nonReparti = Number(row.allocated) - Number(row.sub_allocated)

  return (
    <section className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {t("budgets.sous.titre", { montant: formatAmount(row.sub_allocated) })}
      </h3>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {budgets.map((budget) => {
          const taux = Number(budget.figures.execution_rate ?? 0)
          return (
            <Card key={budget.id} className="border-border/60 shadow-sm">
              <CardContent className="pt-6">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">
                      {budget.scope_label ?? budget.country_name}
                    </p>
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                      {t(`budgets.portee.${budget.scope_kind}`)}
                      {!budget.is_active && (
                        <Badge className={STATUS_TONES.ARCHIVE}>{t("budgets.inactive")}</Badge>
                      )}
                    </p>
                  </div>
                  {canEdit && (
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("budgets.sous.modifier_aria", {
                        enveloppe: budget.scope_label ?? budget.country_name,
                      })}
                      onClick={() => onEdit(budget)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  )}
                </div>
                <div className="mt-4 flex items-center gap-4">
                  <Jauge
                    rate={budget.figures.execution_rate}
                    label={formatRate(budget.figures.execution_rate)}
                    over={taux > 1}
                    near={taux >= warningRate}
                    title={t("budgets.sous.jauge_aria", {
                      enveloppe: budget.scope_label ?? budget.country_name,
                      taux: formatRate(budget.figures.execution_rate),
                    })}
                  />
                  <dl className="min-w-0 space-y-2">
                    <div>
                      <dt className="text-xs text-muted-foreground">
                        {t("budgets.enveloppe.attribue")}
                      </dt>
                      <dd className="text-sm font-semibold">{formatAmount(budget.amount)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted-foreground">
                        {t("budgets.colonnes.disponible")}
                      </dt>
                      <dd
                        className={cn(
                          "text-sm font-semibold",
                          Number(budget.figures.remaining) < 0
                            ? "text-destructive"
                            : taux >= warningRate
                              ? "text-statut-attente"
                              : "text-marque-fort",
                        )}
                      >
                        {formatAmount(budget.figures.remaining)}
                      </dd>
                    </div>
                  </dl>
                </div>
              </CardContent>
            </Card>
          )
        })}

        {canCreate && (
          <button
            type="button"
            onClick={onCreate}
            className="flex flex-col items-start justify-center gap-2 rounded-xl border border-dashed border-border p-6 text-left transition-colors hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Plus className="h-4 w-4 text-muted-foreground" aria-hidden />
            <span className="text-sm font-semibold">{t("budgets.sous.decouper")}</span>
            <span className="text-xs text-muted-foreground">
              {nonReparti > 0
                ? t("budgets.sous.non_reparti", { montant: formatAmount(String(nonReparti)) })
                : t("budgets.sous.tout_reparti")}
            </span>
          </button>
        )}
      </div>
    </section>
  )
}
