import { useState, type FormEvent } from "react"
import { ArrowRight, ArrowRightLeft, Check, Loader2, Plus, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { FormError } from "@/components/ui/form-error"
import { MontantNormalise } from "@/components/ui/montant-normalise"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import {
  approveReallocation,
  createReallocation,
  fetchReallocations,
  rejectReallocation,
} from "@/lib/budgets"
import {
  REALLOCATION_CARD_STYLE,
  REALLOCATION_FLOW_STYLE,
  REALLOCATION_STYLE,
} from "@/lib/status-styles"
import type { Budget, Reallocation } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn, formatAmount, formatDate, normalizeDecimal } from "@/lib/utils"

interface ReallocationsProps {
  budgets: Budget[]
  /** Demander un transfert (`reallocations.request`). L'arbitrage, lui,
   * vient ligne par ligne du serveur (`can_decide`). */
  canRequest: boolean
  onChanged: () => void
}

export function Reallocations({ budgets, canRequest, onChanged }: ReallocationsProps) {
  const { t } = useTranslation()
  const query = useQuery(
    "reallocations",
    (signal) => fetchReallocations({ page_size: 100 }, signal),
  )
  const rows = query.data?.results ?? []
  const [error, setError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [rejecting, setRejecting] = useState<Reallocation | null>(null)

  // La demande ne porte que le libellé de ses deux enveloppes ; leur solde se
  // retrouve dans la liste des enveloppes de l'écran. Une enveloppe hors de
  // cette liste — un autre exercice — n'en affiche aucun.
  const disponibleDe = (id: number) =>
    budgets.find((budget) => budget.id === id)?.figures.remaining ?? null

  const handleApprove = async (row: Reallocation) => {
    setBusyId(row.id)
    setError(null)
    try {
      await approveReallocation(row.id)
      query.reload()
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : t("budgets.realloc.approbation_impossible"))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t("budgets.realloc.titre")}</h3>
          <p className="text-xs text-muted-foreground">
            {t("budgets.realloc.description")}
          </p>
        </div>
        {canRequest && (
          <Button size="sm" onClick={() => setFormOpen(true)}>
            <Plus className="mr-1 h-4 w-4" aria-hidden />
            {t("budgets.realloc.demander")}
          </Button>
        )}
      </div>

      <FormError>{error ?? query.error}</FormError>
      <TruncatedNotice page={query.data} noun={t("budgets.realloc.nom_pluriel")} />

      {/* Un transfert se lit d'un bout à l'autre : l'enveloppe qui donne, le
          montant, l'enveloppe qui reçoit — puis qui a demandé et qui tranche.
          Le tableau coupait ce mouvement en cinq colonnes. */}
      {query.loading ? (
        <div className="space-y-2" aria-busy="true">
          {[0, 1].map((rang) => (
            <div key={rang} className="h-24 animate-pulse rounded-lg border border-border/60 bg-muted/40" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border/60 p-8 text-center">
          <ArrowRightLeft className="mx-auto h-5 w-5 text-muted-foreground" aria-hidden />
          <p className="mt-2 text-sm font-medium">{t("budgets.realloc.vide_titre")}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {canRequest
              ? t("budgets.realloc.vide_indication_siege")
              : t("budgets.realloc.vide_indication_pays")}
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => {
            // Les teintes viennent de `status-styles` : la carte s'allume tant
            // que la demande attend, le flux s'éteint une fois tranchée.
            const flux = REALLOCATION_FLOW_STYLE[row.status]
            return (
              <li
                key={row.id}
                className={cn("rounded-lg border p-3", REALLOCATION_CARD_STYLE[row.status])}
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                  <div className="flex flex-1 items-stretch gap-3">
                    <Enveloppe
                      role={t("champs.source")}
                      label={row.source_label}
                      disponible={disponibleDe(row.source)}
                      tone={flux.enveloppe}
                    />
                    <div className="flex shrink-0 flex-col items-center justify-center gap-1">
                      <span className={cn("text-sm font-semibold", flux.accent)}>
                        {formatAmount(row.amount)}
                      </span>
                      {/* La flèche est un dessin : le sens du transfert est dit
                          aux lecteurs d'écran en `sr-only`, un `aria-label` sur
                          un `<svg>` sans rôle n'étant pas lu. */}
                      <ArrowRight className={cn("h-4 w-8", flux.accent)} aria-hidden />
                      <span className="sr-only">{t("budgets.realloc.vers")}</span>
                    </div>
                    <Enveloppe
                      role={t("champs.target")}
                      label={row.target_label}
                      disponible={disponibleDe(row.target)}
                      tone={flux.enveloppe}
                    />
                  </div>

                  <span aria-hidden className="hidden w-px self-stretch bg-border lg:block" />

                  <div className="lg:w-64">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge className={REALLOCATION_STYLE[row.status]}>{row.status_display}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {row.requested_by
                          ? t("budgets.realloc.par", { auteur: row.requested_by })
                          : null}
                        {row.requested_by && " · "}
                        {formatDate(row.created_at)}
                      </span>
                    </div>
                    <p className="mt-2 text-xs italic text-muted-foreground">{row.reason}</p>
                    {row.decision_note && (
                      <p className="mt-1 text-xs italic text-muted-foreground">
                        {t("budgets.realloc.decision", { note: row.decision_note })}
                      </p>
                    )}
                  </div>

                  {/* Le serveur dit qui tranche (`can_decide`) : demande encore
                      en attente, rôle décideur, pas son auteur. */}
                  {row.can_decide && (
                    <div className="flex shrink-0 gap-2 lg:flex-col">
                      <Button
                        size="sm"
                        disabled={busyId === row.id}
                        onClick={() => void handleApprove(row)}
                      >
                        {busyId === row.id ? (
                          <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden />
                        ) : (
                          <Check className="mr-1 h-4 w-4" aria-hidden />
                        )}
                        {t("budgets.realloc.approuver")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive hover:text-destructive"
                        // Même garde que « Approuver » : ouvrir le refus
                        // pendant que l'approbation part rapportait un refus
                        // incompréhensible du serveur.
                        disabled={busyId === row.id}
                        onClick={() => setRejecting(row)}
                      >
                        <X className="mr-1 h-4 w-4" aria-hidden />
                        {t("budgets.realloc.refuser")}
                      </Button>
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}

      {formOpen && (
        <ReallocationForm
          onOpenChange={setFormOpen}
          budgets={budgets}
          onSaved={async () => {
            query.reload()
            onChanged()
          }}
        />
      )}

      {rejecting && (
        <RejectDialog
          key={rejecting.id}
          reallocation={rejecting}
          onClose={() => setRejecting(null)}
          onRejected={async () => {
            query.reload()
            onChanged()
          }}
        />
      )}
    </div>
  )
}

/** Un bout de flux : l'enveloppe qui donne ou celle qui reçoit, et son solde. */
function Enveloppe({
  role,
  label,
  disponible,
  tone,
}: {
  role: string
  label: string
  disponible: string | null
  /** Bordure et fond, selon l'état de la demande (`REALLOCATION_FLOW_STYLE`). */
  tone: string
}) {
  const { t } = useTranslation()
  return (
    <div className={cn("min-w-0 flex-1 rounded-lg border p-2.5", tone)}>
      <p className="text-xs text-muted-foreground">{role}</p>
      <p className="mt-1 truncate text-sm font-semibold">{label}</p>
      {disponible !== null && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          {t("budgets.realloc.disponibles", { montant: formatAmount(disponible) })}
        </p>
      )}
    </div>
  )
}

function ReallocationForm({
  onOpenChange,
  budgets,
  onSaved,
}: {
  onOpenChange: (open: boolean) => void
  budgets: Budget[]
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [source, setSource] = useState<number | "">(budgets[0]?.id ?? "")
  const [target, setTarget] = useState<number | "">(budgets[1]?.id ?? "")
  const [amount, setAmount] = useState("")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const montant = normalizeDecimal(amount)
    if (montant === null) {
      setError(t("budgets.realloc.montant_requis"))
      return
    }
    // Les enveloppes arrivent parfois après l'ouverture du formulaire : le
    // choix reste vide tant qu'on n'en a pas nommé une, et un vide ne part
    // pas au serveur.
    if (source === "" || target === "") {
      setError(t("budgets.realloc.enveloppes_requises"))
      return
    }
    if (source === target) {
      setError(t("budgets.realloc.enveloppes_identiques"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await createReallocation({ source, target, amount: montant, reason })
      await onSaved()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : t("budgets.realloc.demande_impossible"))
    } finally {
      setSaving(false)
    }
  }

  const libelle = (b: Budget) =>
    `${b.country_name} ${b.year}${b.scope_label ? ` — ${b.scope_label}` : ""}`

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("budgets.realloc.form_titre")}</DialogTitle>
          <DialogDescription>{t("budgets.realloc.form_description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="realloc-source">{t("champs.source")}</Label>
            <NativeSelect
              id="realloc-source"
              value={source}
              onChange={(e) => setSource(e.target.value === "" ? "" : Number(e.target.value))}
            >
              <option value="">{t("budgets.realloc.choisir_enveloppe")}</option>
              {budgets.map((b) => (
                <option key={b.id} value={b.id}>
                  {t("budgets.realloc.option_source", {
                    libelle: libelle(b),
                    montant: formatAmount(b.figures.remaining, b.currency),
                  })}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="realloc-target">{t("champs.target")}</Label>
            <NativeSelect
              id="realloc-target"
              value={target}
              onChange={(e) => setTarget(e.target.value === "" ? "" : Number(e.target.value))}
            >
              <option value="">{t("budgets.realloc.choisir_enveloppe")}</option>
              {budgets.map((b) => (
                <option key={b.id} value={b.id}>
                  {libelle(b)}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="realloc-amount">{t("commun.montant")}</Label>
            <Input
              id="realloc-amount"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
            <MontantNormalise value={amount} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="realloc-reason">{t("budgets.realloc.colonnes.justification")}</Label>
            <Textarea
              id="realloc-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t("budgets.realloc.motif_placeholder")}
              required
            />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("budgets.realloc.envoyer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RejectDialog({
  reallocation,
  onClose,
  onRejected,
}: {
  reallocation: Reallocation
  onClose: () => void
  onRejected: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!note.trim()) {
      setError(t("budgets.realloc.motif_requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await rejectReallocation(reallocation.id, note.trim())
      await onRejected()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : t("budgets.realloc.refus_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("budgets.realloc.refus_titre")}</DialogTitle>
          <DialogDescription>{t("budgets.realloc.refus_description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="reject-note">{t("budgets.realloc.motif_refus")}</Label>
            <Textarea
              id="reject-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              required
            />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={onClose}>
                {t("commun.annuler")}
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={saving}
                className="ml-2"
              >
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("budgets.realloc.refuser")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
