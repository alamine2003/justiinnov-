import { useState, type FormEvent } from "react"
import { AlertTriangle, Coins, Loader2, Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
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
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { createExchangeRate, fetchExchangeRates } from "@/lib/budgets"
import { STATUS_TONES } from "@/lib/status-styles"
import { useQuery } from "@/lib/use-query"
import { formatAmount, formatDay, normalizeDecimal, todayIso } from "@/lib/utils"

/**
 * Taux de change vers le FCFA.
 *
 * Un taux ne se corrige pas : on en publie un nouveau, daté. Les conversions
 * déjà calculées gardent le taux en vigueur à leur date, sinon un rapport
 * imprimé hier ne serait plus reproductible aujourd'hui.
 */
export function RatesSection() {
  const { t } = useTranslation()
  const query = useQuery(
    "exchange-rates",
    (signal) => fetchExchangeRates({ page_size: 100 }, signal),
    { fallback: t("configuration.taux.indisponibles") },
  )
  const rates = query.data?.results ?? []
  const [open, setOpen] = useState(false)

  // Les taux arrivent triés par devise puis date décroissante : le premier de
  // chaque devise est donc celui qui s'applique aujourd'hui.
  const enVigueur = new Set<string>()
  const courants = new Set<number>()
  for (const rate of rates) {
    if (!enVigueur.has(rate.currency)) {
      enVigueur.add(rate.currency)
      courants.add(rate.id)
    }
  }

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-3">
        <div>
          <CardTitle className="text-sm font-semibold">
            {t("configuration.taux.titre")}
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("configuration.taux.description")}
          </p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="mr-2 h-4 w-4" aria-hidden />
          {t("configuration.taux.publier")}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {query.error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>{t("commun.erreur")}</AlertTitle>
            <AlertDescription>{query.error}</AlertDescription>
          </Alert>
        )}
        <TruncatedNotice page={query.data} noun={t("configuration.taux.noun")} />

        <div className="overflow-x-auto rounded-lg border border-border/60">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">{t("commun.devise")}</TableHead>
                <TableHead scope="col" className="text-right">
                  {t("configuration.taux.col_unite")}
                </TableHead>
                <TableHead scope="col">{t("champs.valid_from")}</TableHead>
                <TableHead scope="col" className="text-right">
                  {t("commun.statut")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.loading ? (
                <SkeletonRows columns={4} rows={3} />
              ) : rates.length === 0 ? (
                <EmptyRow
                  colSpan={4}
                  icon={Coins}
                  title={t("configuration.taux.vide_titre")}
                  hint={t("configuration.taux.vide_aide")}
                />
              ) : (
                rates.map((rate) => (
                  <TableRow key={rate.id}>
                    <TableCell className="font-medium">{rate.currency}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatAmount(rate.rate_to_xof, undefined, { maxFractionDigits: 6 })}
                    </TableCell>
                    <TableCell>{formatDay(rate.valid_from)}</TableCell>
                    <TableCell className="text-right">
                      {courants.has(rate.id) ? (
                        <Badge className={STATUS_TONES.SUCCES}>
                          {t("configuration.taux.en_vigueur")}
                        </Badge>
                      ) : (
                        <Badge variant="outline">
                          {t("configuration.taux.historique")}
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>

      {open && (
        <RateForm
          onOpenChange={setOpen}
          onSaved={() => query.reload()}
        />
      )}
    </Card>
  )
}

function RateForm({
  onOpenChange,
  onSaved,
}: {
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const [currency, setCurrency] = useState("")
  const [rate, setRate] = useState("")
  const [validFrom, setValidFrom] = useState(todayIso())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const taux = normalizeDecimal(rate)
    if (currency.trim().length !== 3) {
      setError(t("configuration.taux.devise_invalide"))
      return
    }
    if (taux === null || Number(taux) <= 0) {
      setError(t("configuration.taux.taux_invalide"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await createExchangeRate({
        currency: currency.trim().toUpperCase(),
        rate_to_xof: taux,
        valid_from: validFrom,
      })
      onSaved()
      onOpenChange(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : t("erreurs.enregistrement_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md shadow-xl">
        <form onSubmit={handleSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>{t("configuration.taux.publier")}</DialogTitle>
            <DialogDescription>
              {t("configuration.taux.dialogue_description")}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <FormError>{error}</FormError>
            <div className="space-y-2">
              <Label htmlFor="rate-currency">{t("configuration.taux.devise_iso")}</Label>
              <Input
                id="rate-currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                maxLength={3}
                placeholder={t("configuration.taux.devise_exemple")}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rate-value">{t("configuration.taux.valeur")}</Label>
              <Input
                id="rate-value"
                inputMode="decimal"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                placeholder={t("configuration.taux.valeur_exemple")}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rate-from">{t("champs.valid_from")}</Label>
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
              {t("commun.annuler")}
            </Button>
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("configuration.taux.publier_action")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
