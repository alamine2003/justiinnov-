import { useState, type FormEvent } from "react"
import { ArrowRight, ArrowRightLeft, Check, Loader2, Plus, X } from "lucide-react"
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
      setError(e instanceof Error ? e.message : "Approbation impossible")
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Réallocations</h3>
          <p className="text-xs text-muted-foreground">
            Transferts entre enveloppes, justifiés et soumis à approbation.
          </p>
        </div>
        {canDecide && (
          <Button size="sm" onClick={() => setFormOpen(true)}>
            <Plus className="mr-1 h-4 w-4" aria-hidden />
            Demander
          </Button>
        )}
      </div>

      <FormError>{error ?? query.error}</FormError>
      <TruncatedNotice page={query.data} noun="réallocations" />

      <div className="overflow-x-auto rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Transfert</TableHead>
              <TableHead scope="col" className="text-right">Montant</TableHead>
              <TableHead scope="col">Justification</TableHead>
              <TableHead scope="col">Statut</TableHead>
              <TableHead scope="col" className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.loading ? (
              <SkeletonRows columns={5} />
            ) : rows.length === 0 ? (
              <EmptyRow
                colSpan={5}
                icon={ArrowRightLeft}
                title="Aucune réallocation"
                hint={
                  canDecide
                    ? "Demandez un transfert pour déplacer un montant d'une enveloppe à une autre."
                    : "Aucun transfert n'a été demandé sur votre périmètre."
                }
              />
            ) : (
              rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <div className="flex items-center gap-2 text-sm">
                      <span>{row.source_label}</span>
                      <ArrowRight className="h-3 w-3 text-muted-foreground" aria-label="vers" />
                      <span>{row.target_label}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(row.created_at)}
                      {row.requested_by && ` · par ${row.requested_by}`}
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
                        Décision : {row.decision_note}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge className={REALLOCATION_STYLE[row.status]}>
                      {row.status_display}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {canDecide && row.status === "pending" && (
                      <>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Approuver"
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
                          aria-label="Refuser"
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
      setError("Indiquez le montant à transférer, en chiffres.")
      return
    }
    if (source === target) {
      setError("Choisissez deux enveloppes différentes.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await createReallocation({ source, target, amount: montant, reason })
      await onSaved()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demande impossible")
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
          <DialogTitle>Demander une réallocation</DialogTitle>
          <DialogDescription>
            Le transfert n'est exécuté qu'après approbation.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="realloc-source">Enveloppe source</Label>
            <NativeSelect
              id="realloc-source"
              value={source}
              onChange={(e) => setSource(Number(e.target.value))}
            >
              {budgets.map((b) => (
                <option key={b.id} value={b.id}>
                  {libelle(b)} ({formatAmount(b.figures.remaining, b.currency)} disponibles)
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="realloc-target">Enveloppe destinataire</Label>
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
            <Label htmlFor="realloc-amount">Montant</Label>
            <Input
              id="realloc-amount"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="realloc-reason">Justification</Label>
            <Textarea
              id="realloc-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Motif du transfert"
              required
            />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Annuler
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Envoyer
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
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!note.trim()) {
      setError("Un refus doit être motivé.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await rejectReallocation(reallocation.id, note.trim())
      await onRejected()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refus impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Refuser la réallocation</DialogTitle>
          <DialogDescription>
            Un refus doit être motivé : le motif est conservé dans l'historique.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="reject-note">Motif du refus</Label>
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
                Annuler
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={saving}
                className="ml-2"
              >
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Refuser
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
