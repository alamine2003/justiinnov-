import { useCallback, useEffect, useState, type FormEvent } from "react"
import { ArrowRight, Check, Loader2, Plus, X } from "lucide-react"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  approveReallocation,
  createReallocation,
  fetchReallocations,
  rejectReallocation,
} from "@/lib/budgets"
import type { Budget, Reallocation, ReallocationStatus } from "@/lib/types"
import { formatAmount, formatDate } from "@/lib/utils"

const STATUS_STYLE: Record<ReallocationStatus, string> = {
  pending: "bg-amber-500 hover:bg-amber-500",
  approved: "bg-emerald-500 hover:bg-emerald-500",
  rejected: "bg-destructive hover:bg-destructive",
}

interface ReallocationsProps {
  budgets: Budget[]
  canDecide: boolean
  onChanged: () => void
}

export function Reallocations({ budgets, canDecide, onChanged }: ReallocationsProps) {
  const [rows, setRows] = useState<Reallocation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [rejecting, setRejecting] = useState<Reallocation | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchReallocations({ page_size: 100 })
      setRows(data.results)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chargement impossible")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleApprove = async (row: Reallocation) => {
    setBusyId(row.id)
    setError(null)
    try {
      await approveReallocation(row.id)
      await load()
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
            <Plus className="mr-1 h-4 w-4" />
            Demander
          </Button>
        )}
      </div>

      {error && (
        <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="overflow-hidden rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Transfert</TableHead>
              <TableHead>Montant</TableHead>
              <TableHead>Justification</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="h-16">
                  <div className="h-4 animate-pulse rounded bg-muted" />
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-16 text-center text-muted-foreground">
                  Aucune réallocation.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <div className="flex items-center gap-2 text-sm">
                      <span>{row.source_label}</span>
                      <ArrowRight className="h-3 w-3 text-muted-foreground" />
                      <span>{row.target_label}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(row.created_at)}
                      {row.requested_by && ` · par ${row.requested_by}`}
                    </p>
                  </TableCell>
                  <TableCell className="font-medium">
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
                    <Badge className={STATUS_STYLE[row.status]}>
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
                          onClick={() => handleApprove(row)}
                        >
                          {busyId === row.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Check className="h-4 w-4 text-emerald-600" />
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

      <ReallocationForm
        open={formOpen}
        onOpenChange={setFormOpen}
        budgets={budgets}
        onSaved={async () => {
          await load()
          onChanged()
        }}
      />

      <RejectDialog
        reallocation={rejecting}
        onClose={() => setRejecting(null)}
        onRejected={async () => {
          await load()
          onChanged()
        }}
      />
    </div>
  )
}

function ReallocationForm({
  open,
  onOpenChange,
  budgets,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  budgets: Budget[]
  onSaved: () => Promise<void>
}) {
  const [source, setSource] = useState<number | "">("")
  const [target, setTarget] = useState<number | "">("")
  const [amount, setAmount] = useState("")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setSource(budgets[0]?.id ?? "")
    setTarget(budgets[1]?.id ?? "")
    setAmount("")
    setReason("")
    setError(null)
  }, [open, budgets])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await createReallocation({ source, target, amount, reason })
      await onSaved()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demande impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Demander une réallocation</DialogTitle>
          <DialogDescription>
            Le transfert n'est exécuté qu'après approbation.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2">
          {error && (
            <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="grid gap-2">
            <Label htmlFor="realloc-source">Enveloppe source</Label>
            <NativeSelect
              id="realloc-source"
              value={source}
              onChange={(e) => setSource(Number(e.target.value))}
            >
              {budgets.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.country_name} {b.year}
                  {b.project_name ? ` — ${b.project_name}` : ""} (
                  {formatAmount(b.amount, b.currency)})
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
                  {b.country_name} {b.year}
                  {b.project_name ? ` — ${b.project_name}` : ""}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="realloc-amount">Montant</Label>
            <Input
              id="realloc-amount"
              type="number"
              step="0.01"
              min="0.01"
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
  reallocation: Reallocation | null
  onClose: () => void
  onRejected: () => Promise<void>
}) {
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setNote("")
    setError(null)
  }, [reallocation])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!reallocation) return
    setSaving(true)
    setError(null)
    try {
      await rejectReallocation(reallocation.id, note)
      await onRejected()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refus impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={reallocation !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Refuser la réallocation</DialogTitle>
          <DialogDescription>
            Un refus doit être motivé : le motif est conservé dans l'historique.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2">
          {error && (
            <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}
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
