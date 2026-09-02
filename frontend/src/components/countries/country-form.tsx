import { useEffect, useState, type FormEvent } from "react"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Switch } from "@/components/ui/switch"
import { fetchAvailableCountries } from "@/lib/countries"
import type { AvailableCountry } from "@/lib/types"

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

export function CountryForm({
  open,
  onOpenChange,
  onSave,
  initial,
  title,
}: CountryFormProps) {
  const [values, setValues] = useState<CountryFormValues>(initial ?? DEFAULTS)
  const [saving, setSaving] = useState(false)
  const [disponibles, setDisponibles] = useState<AvailableCountry[]>([])
  const creation = !initial

  // Chargée à l'ouverture seulement : la liste change dès qu'un pays est créé.
  useEffect(() => {
    if (!open || !creation) return
    void fetchAvailableCountries()
      .then(setDisponibles)
      .catch(() => setDisponibles([]))
  }, [open, creation])

  const setField = (field: keyof CountryFormValues, value: unknown) => {
    setValues((v) => ({ ...v, [field]: value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await onSave(values)
      setValues(DEFAULTS)
      onOpenChange(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setValues(DEFAULTS)
        onOpenChange(o)
      }}
    >
      <DialogContent className="sm:max-w-lg shadow-xl">
        <DialogHeader>
          <DialogTitle>{title ?? "Ajouter un pays"}</DialogTitle>
          <DialogDescription>
            Choisissez le pays, puis sa devise et son fuseau horaire.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2">
          {creation ? (
            <div className="grid gap-2">
              <Label htmlFor="pays">Pays</Label>
              <NativeSelect
                id="pays"
                value={values.code}
                onChange={(e) => {
                  const choisi = disponibles.find((p) => p.code === e.target.value)
                  setValues((v) => ({
                    ...v,
                    code: choisi?.code ?? "",
                    name: choisi?.name ?? "",
                  }))
                }}
                required
              >
                <option value="">Choisir un pays…</option>
                {disponibles.map((pays) => (
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
              <p className="text-sm font-medium">Pays actif</p>
              <p className="text-xs text-muted-foreground">
                Désactivé, le pays reste consultable mais n'apparaît plus dans les listes actives.
              </p>
            </div>
            <Switch
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
      </DialogContent>
    </Dialog>
  )
}