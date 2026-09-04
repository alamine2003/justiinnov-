import { useState, type FormEvent } from "react"
import { Loader2 } from "lucide-react"
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
  const [values, setValues] = useState<CountryFormValues>(initial ?? DEFAULTS)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const creation = !initial

  // Chargée à l'ouverture seulement : la liste change dès qu'un pays est créé.
  const disponibles = useQuery("countries:disponibles", () => fetchAvailableCountries(), {
    enabled: creation,
    fallback: "Liste des pays indisponible",
  })

  const setField = (field: keyof CountryFormValues, value: unknown) => {
    setValues((v) => ({ ...v, [field]: value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (creation && !values.code) {
      setError("Choisissez un pays dans la liste.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(values)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enregistrement impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{title ?? "Ajouter un pays"}</DialogTitle>
        <DialogDescription>
          Choisissez le pays, puis sa devise et son fuseau horaire.
        </DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
        <FormError>{error ?? disponibles.error}</FormError>
        {creation ? (
          <div className="grid gap-2">
            <Label htmlFor="pays">Pays</Label>
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
                {disponibles.loading ? "Chargement…" : "Choisir un pays…"}
              </option>
              {(disponibles.data ?? []).map((pays) => (
                <option key={pays.code} value={pays.code}>
                  {pays.name} ({pays.code})
                </option>
              ))}
            </NativeSelect>
            <p className="text-xs text-muted-foreground">
              La plateforme suit les filiales africaines du groupe. Les pays
              déjà enregistrés n'apparaissent pas dans cette liste.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Nom</Label>
              <Input
                id="name"
                value={values.name}
                onChange={(e) => setField("name", e.target.value)}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="code">Code ISO</Label>
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
            <Label htmlFor="currency">Devise (ISO 4217)</Label>
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
            <Label htmlFor="currency_symbol">Symbole</Label>
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
          <Label htmlFor="timezone">Fuseau horaire</Label>
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
            <Label htmlFor="country-active" className="text-sm font-medium">Pays actif</Label>
            <p className="text-xs text-muted-foreground">
              Désactivé, le pays reste consultable mais n'apparaît plus dans les listes actives.
            </p>
          </div>
          <Switch
            id="country-active"
            checked={values.is_active}
            onCheckedChange={(c) => setField("is_active", c)}
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Annuler
          </Button>
          <Button type="submit" disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Enregistrer
          </Button>
        </DialogFooter>
      </form>
    </>
  )
}
