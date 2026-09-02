import { useCallback, useEffect, useState, type FormEvent } from "react"
import { AlertTriangle, Loader2, Plus } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { createExchangeRate, fetchExchangeRates } from "@/lib/budgets"
import { formatDate } from "@/lib/utils"
import type { ExchangeRate } from "@/lib/types"

/**
 * Taux de change vers le FCFA.
 *
 * Un taux ne se corrige pas : on en publie un nouveau, daté. Les conversions
 * déjà calculées gardent le taux en vigueur à leur date, sinon un rapport
 * imprimé hier ne serait plus reproductible aujourd'hui.
 */
export function RatesSection() {
  const [rates, setRates] = useState<ExchangeRate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchExchangeRates({ page_size: 100 })
      setRates(data.results)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chargement impossible")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // Les taux arrivent triés par devise puis date décroissante : le premier de
  // chaque devise est donc celui qui s'applique aujourd'hui.
  const enVigueur = new Set<string>()
  const courants = rates.filter((r) => {
    if (enVigueur.has(r.currency)) return false
    enVigueur.add(r.currency)
    return true
  })

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-3">
        <div>
          <CardTitle className="text-sm font-semibold">
            Taux de change vers le FCFA
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Un taux ne se modifie pas : publiez-en un nouveau, daté. Les montants
            déjà consolidés conservent le taux de leur date.
          </p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Publier un taux
        </Button>
      </CardHeader>
      <CardContent>
        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Erreur</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="overflow-x-auto rounded-lg border border-border/60">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Devise</TableHead>
                <TableHead className="text-right">1 unité en FCFA</TableHead>
                <TableHead>En vigueur depuis</TableHead>
                <TableHead className="text-right">Statut</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center">
                    <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
                  </TableCell>
                </TableRow>
              )}
              {!loading && rates.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={4}
                    className="py-8 text-center text-sm text-muted-foreground"
                  >
                    Aucun taux publié. Les pays hors zone FCFA ne seront pas
                    consolidés tant qu'aucun taux n'existe.
                  </TableCell>
                </TableRow>
              )}
              {rates.map((rate) => {
                const courant = courants.includes(rate)
                return (
                  <TableRow key={rate.id}>
                    <TableCell className="font-medium">{rate.currency}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {rate.rate_to_xof}
                    </TableCell>
                    <TableCell>{formatDate(rate.valid_from)}</TableCell>
                    <TableCell className="text-right">
                      {courant ? (
                        <Badge className="bg-emerald-500 hover:bg-emerald-500">
                          en vigueur
                        </Badge>
                      ) : (
                        <Badge variant="outline">historique</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>

      <RateForm
        open={open}
        onOpenChange={setOpen}
        onSaved={() => {
          void load()
        }}
      />
    </Card>
  )
}

function RateForm({
  open,
  onOpenChange,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const aujourdhui = new Date().toISOString().slice(0, 10)
  const [currency, setCurrency] = useState("")
  const [rate, setRate] = useState("")
  const [validFrom, setValidFrom] = useState(aujourdhui)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setCurrency("")
    setRate("")
    setValidFrom(aujourdhui)
    setError(null)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await createExchangeRate({
        currency: currency.toUpperCase(),
        rate_to_xof: rate,
        valid_from: validFrom,
      })
      reset()
      onOpenChange(false)
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Enregistrement impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) reset()
        onOpenChange(o)
      }}
    >
      <DialogContent className="sm:max-w-md shadow-xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Publier un taux</DialogTitle>
            <DialogDescription>
              Combien de FCFA vaut une unité de cette devise, et à partir de
              quand.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {error && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="space-y-2">
              <Label htmlFor="rate-currency">Devise (ISO 4217)</Label>
              <Input
                id="rate-currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                maxLength={3}
                placeholder="EUR"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rate-value">1 unité vaut (FCFA)</Label>
              <Input
                id="rate-value"
                type="number"
                step="0.000001"
                min="0.000001"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                placeholder="655.957000"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rate-from">En vigueur depuis</Label>
              <Input
                id="rate-from"
                type="date"
                value={validFrom}
                onChange={(e) => setValidFrom(e.target.value)}
                required
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Annuler
            </Button>
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Publier
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
