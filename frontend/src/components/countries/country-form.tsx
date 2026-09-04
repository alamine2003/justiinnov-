import { useState, type FormEvent } from "react"
import { Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"
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
import { Switch } from "@/components/ui/switch"
import { fetchAvailableCountries } from "@/lib/countries"
import { useQuery } from "@/lib/use-query"

export interface CountryFormValues {
  name: string
  code: string
  currency: string
  currency_symbol: string
  timezone: string
  is_active: boolean
}

interface CountryFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (values: CountryFormValues) => Promise<void>
  initial?: CountryFormValues
  title?: string
}

const DEFAULTS: CountryFormValues = {
  name: "",
  code: "",
  currency: "",
  currency_symbol: "",
  timezone: "UTC",
  is_active: true,
}

export function CountryForm({ open, onOpenChange, ...rest }: CountryFormProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg shadow-xl">
        {/* Monté à l'ouverture : les valeurs repartent du pays édité, ce
            qu'un état initialisé une fois au premier rendu ne faisait pas. */}
        {open && <CountryFormBody key={rest.initial?.code ?? "nouveau"} onOpenChange={onOpenChange} {...rest} />}
      </DialogContent>
    </Dialog>
  )
}

function CountryFormBody({
  onOpenChange,
  onSave,
  initial,
  title,
}: Omit<CountryFormProps, "open">) {
  const { t } = useTranslation()
  const [values, setValues] = useState<CountryFormValues>(initial ?? DEFAULTS)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const creation = !initial

  // Chargée à l'ouverture seulement : la liste change dès qu'un pays est créé.
  const disponibles = useQuery("countries:disponibles", () => fetchAvailableCountries(), {
    enabled: creation,
    fallback: t("pays.formulaire.liste_indisponible"),
  })

  const setField = (field: keyof CountryFormValues, value: unknown) => {
    setValues((v) => ({ ...v, [field]: value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (creation && !values.code) {
      setError(t("pays.formulaire.choix_requis"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(values)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : t("erreurs.enregistrement_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{title ?? t("pays.formulaire.titre_ajout")}</DialogTitle>
        <DialogDescription>{t("pays.formulaire.description")}</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
        <FormError>{error ?? disponibles.error}</FormError>
        {creation ? (
          <div className="grid gap-2">
            <Label htmlFor="pays">{t("commun.pays")}</Label>
            <NativeSelect
              id="pays"
              value={values.code}
              onChange={(e) => {
                const choisi = disponibles.data?.find((p) => p.code === e.target.value)
                setValues((v) => ({
                  ...v,
                  code: choisi?.code ?? "",
                  name: choisi?.name ?? "",
                }))
              }}
              disabled={disponibles.loading}
              required
            >
              <option value="">
                {disponibles.loading ? t("commun.chargement") : t("pays.formulaire.choisir")}
              </option>
              {(disponibles.data ?? []).map((pays) => (
                <option key={pays.code} value={pays.code}>
                  {pays.name} ({pays.code})
                </option>
              ))}
            </NativeSelect>
            <p className="text-xs text-muted-foreground">{t("pays.formulaire.note_afrique")}</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="name">{t("champs.name")}</Label>
              <Input
                id="name"
                value={values.name}
                onChange={(e) => setField("name", e.target.value)}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="code">{t("pays.formulaire.code_iso")}</Label>
              <Input
                id="code"
                value={values.code}
                onChange={(e) => setField("code", e.target.value.toUpperCase())}
                maxLength={2}
                required
              />
            </div>
          </div>
        )}
        <div className="grid grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label htmlFor="currency">{t("pays.formulaire.devise_iso")}</Label>
            <Input
              id="currency"
              value={values.currency}
              onChange={(e) => setField("currency", e.target.value.toUpperCase())}
              placeholder="XOF"
              maxLength={3}
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="currency_symbol">{t("pays.formulaire.symbole")}</Label>
            <Input
              id="currency_symbol"
              value={values.currency_symbol}
              onChange={(e) => setField("currency_symbol", e.target.value)}
              placeholder="FCFA"
              maxLength={4}
            />
          </div>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="timezone">{t("champs.timezone")}</Label>
          <Input
            id="timezone"
            value={values.timezone}
            onChange={(e) => setField("timezone", e.target.value)}
            placeholder="Africa/Porto-Novo"
            required
          />
        </div>
        <div className="flex items-center justify-between rounded-lg border p-3">
          <div>
            <Label htmlFor="country-active" className="text-sm font-medium">
              {t("pays.formulaire.actif_label")}
            </Label>
            <p className="text-xs text-muted-foreground">{t("pays.formulaire.actif_aide")}</p>
          </div>
          <Switch
            id="country-active"
            checked={values.is_active}
            onCheckedChange={(c) => setField("is_active", c)}
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t("commun.annuler")}
          </Button>
          <Button type="submit" disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("commun.enregistrer")}
          </Button>
        </DialogFooter>
      </form>
    </>
  )
}
