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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import {
  approveReallocation,
  createReallocation,
  fetchReallocations,
  rejectReallocation,
} from "@/lib/budgets"
import { REALLOCATION_STYLE } from "@/lib/status-styles"
import type { Budget, Reallocation } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { formatAmount, formatDate, normalizeDecimal } from "@/lib/utils"

interface ReallocationsProps {
  budgets: Budget[]
  canDecide: boolean
  onChanged: () => void
}

export function Reallocations({ budgets, canDecide, onChanged }: ReallocationsProps) {
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
        {canDecide && (
          <Button size="sm" onClick={() => setFormOpen(true)}>
            <Plus className="mr-1 h-4 w-4" aria-hidden />
            {t("budgets.realloc.demander")}
          </Button>
        )}
      </div>

      <FormError>{error ?? query.error}</FormError>
      <TruncatedNotice page={query.data} noun={t("budgets.realloc.nom_pluriel")} />

      <div className="overflow-x-auto rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">{t("budgets.realloc.colonnes.transfert")}</TableHead>
              <TableHead scope="col" className="text-right">{t("commun.montant")}</TableHead>
              <TableHead scope="col">{t("budgets.realloc.colonnes.justification")}</TableHead>
              <TableHead scope="col">{t("commun.statut")}</TableHead>
              <TableHead scope="col" className="text-right">{t("commun.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.loading ? (
              <SkeletonRows columns={5} />
            ) : rows.length === 0 ? (
              <EmptyRow
                colSpan={5}
                icon={ArrowRightLeft}
                title={t("budgets.realloc.vide_titre")}
                hint={
                  canDecide
                    ? t("budgets.realloc.vide_indication_siege")
                    : t("budgets.realloc.vide_indication_pays")
                }
              />
            ) : (
              rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <div className="flex items-center gap-2 text-sm">
                      <span>{row.source_label}</span>
                      <ArrowRight className="h-3 w-3 text-muted-foreground" aria-label={t("budgets.realloc.vers")} />
                      <span>{row.target_label}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(row.created_at)}
                      {row.requested_by &&
                        ` · ${t("budgets.realloc.par", { auteur: row.requested_by })}`}
                    </p>
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    {formatAmount(row.amount)}
                  </TableCell>
                  <TableCell className="max-w-xs">
                    <p className="line-clamp-2 text-xs text-muted-foreground">
                      {row.reason}
                    </p>
                    {row.decision_note && (
                      <p className="line-clamp-2 text-xs italic text-muted-foreground">
                        {t("budgets.realloc.decision", { note: row.decision_note })}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge className={REALLOCATION_STYLE[row.status]}>
                      {row.status_display}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {/* Le serveur dit qui tranche (`can_decide`) : demande
                        encore en attente, rôle décideur, pas son auteur. */}
                    {row.can_decide && (
                      <>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("budgets.realloc.approuver")}
                          disabled={busyId === row.id}
                          onClick={() => void handleApprove(row)}
                        >
                          {busyId === row.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Check className="h-4 w-4 text-statut-succes" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("budgets.realloc.refuser")}
                          className="text-destructive hover:text-destructive"
                          onClick={() => setRejecting(row)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

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
              onChange={(e) => setSource(Number(e.target.value))}
            >
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
              onChange={(e) => setTarget(Number(e.target.value))}
            >
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
