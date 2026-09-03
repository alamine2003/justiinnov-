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
import { Textarea } from "@/components/ui/textarea"
import type { Beneficiary, Expense, Project, Team } from "@/lib/types"

const PAYMENT_METHODS: Record<string, string> = {
  cash: "Espèces",
  transfer: "Virement",
  mobile: "Mobile money",
  card: "Carte",
  check: "Chèque",
  other: "Autre",
}

interface ExpenseFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (values: Record<string, unknown>) => Promise<void>
  editing: Expense | null
  teams: Team[]
  projects: Project[]
  beneficiaries: Beneficiary[]
  currency: string
}

/** Convertit une date ISO en valeur d'``<input type="datetime-local">``. */
function toLocalInput(iso: string) {
  const date = new Date(iso)
  const offset = date.getTimezoneOffset() * 60000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

export function ExpenseForm({
  open,
  onOpenChange,
  onSave,
  editing,
  teams,
  projects,
  beneficiaries,
  currency,
}: ExpenseFormProps) {
  const [title, setTitle] = useState("")
  const [date, setDate] = useState(toLocalInput(new Date().toISOString()))
  const [place, setPlace] = useState("")
  const [amount, setAmount] = useState("")
  // Devise du décaissement : vide tant que la dépense est faite dans la
  // devise du pays, cas de très loin le plus fréquent.
  const [devise, setDevise] = useState("")
  const [montantDevise, setMontantDevise] = useState("")
  const [justified, setJustified] = useState("0")
  const [team, setTeam] = useState<number | "">("")
  const [project, setProject] = useState<number | "">("")
  const [beneficiary, setBeneficiary] = useState<number | "">("")
  const [payment, setPayment] = useState("cash")
  const [description, setDescription] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setError(null)
    if (editing) {
      setTitle(editing.title)
      setDate(toLocalInput(editing.date))
      setPlace(editing.place)
      setAmount(editing.amount)
      setDevise(editing.original_currency ?? "")
      setMontantDevise(editing.original_amount ?? "")
      setJustified(editing.justified_amount)
      setTeam(editing.team ?? "")
      setProject(editing.project ?? "")
      setBeneficiary(editing.beneficiary ?? "")
      setPayment(editing.payment_method)
      setDescription(editing.description)
    } else {
      setTitle("")
      setDate(toLocalInput(new Date().toISOString()))
      setPlace("")
      setAmount("")
      setDevise("")
      setMontantDevise("")
      setJustified("0")
      setTeam("")
      setProject("")
      setBeneficiary("")
      setPayment("cash")
      setDescription("")
    }
  }, [open, editing])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const enDeviseEtrangere = devise.trim() !== "" && montantDevise !== ""
      await onSave({
        title,
        date: new Date(date).toISOString(),
        place,
        // En devise étrangère, le serveur calcule le montant du pays : le lui
        // envoyer serait lui proposer un taux, ce qui n'est pas au pays d'en
        // décider.
        amount: enDeviseEtrangere ? undefined : amount,
        original_currency: enDeviseEtrangere ? devise.trim().toUpperCase() : "",
        original_amount: enDeviseEtrangere ? montantDevise : null,
        justified_amount: justified || "0",
        team: team === "" ? null : team,
        project: project === "" ? null : project,
        beneficiary: beneficiary === "" ? null : beneficiary,
        payment_method: payment,
        description,
      })
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enregistrement impossible")
    } finally {
      setSaving(false)
    }
  }

  const devisePresente = devise.trim() !== ""
  const gap = (Number(amount || 0) - Number(justified || 0)).toLocaleString("fr-FR")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editing ? "Modifier la dépense" : "Ajouter une dépense"}
          </DialogTitle>
          <DialogDescription>
            L'écart est calculé par le serveur : dépense moins montant justifié.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2">
          {error && (
            <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}

          <div className="grid gap-2">
            <Label htmlFor="exp-title">Libellé de la transaction</Label>
            <Input
              id="exp-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Carburant mission Lomé"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="exp-date">Date et heure</Label>
              <Input
                id="exp-date"
                type="datetime-local"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="exp-place">Lieu</Label>
              <Input
                id="exp-place"
                value={place}
                onChange={(e) => setPlace(e.target.value)}
                placeholder="Lomé"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="exp-amount">Dépense ({currency})</Label>
              <Input
                id="exp-amount"
                type="number"
                step="0.01"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                disabled={devisePresente}
                placeholder={devisePresente ? "converti par le serveur" : undefined}
                required={!devisePresente}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="exp-justified">Montant justifié</Label>
              <Input
                id="exp-justified"
                type="number"
                step="0.01"
                min="0"
                value={justified}
                onChange={(e) => setJustified(e.target.value)}
              />
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            Écart calculé : <span className="font-medium">{gap}</span> {currency}
          </p>

          {/* Décaissement dans une autre devise (§5.3). Replié par défaut :
              la quasi-totalité des dépenses est faite dans la devise du pays,
              et deux champs de plus alourdiraient chaque saisie. */}
          <details
            className="rounded-lg border border-border/60 p-3"
            open={devisePresente}
          >
            <summary className="cursor-pointer text-sm font-medium">
              Payé dans une autre devise
            </summary>
            <p className="mt-2 text-xs text-muted-foreground">
              Saisissez le montant tel qu'il figure sur la pièce. Le serveur le
              convertit en {currency} au taux du jour de la dépense et fige ce
              taux : le chiffre ne bougera plus.
            </p>
            <div className="mt-3 grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="exp-devise">Devise (ISO 4217)</Label>
                <Input
                  id="exp-devise"
                  value={devise}
                  onChange={(e) => setDevise(e.target.value.toUpperCase())}
                  maxLength={3}
                  placeholder="EUR"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="exp-montant-devise">Montant décaissé</Label>
                <Input
                  id="exp-montant-devise"
                  type="number"
                  step="0.01"
                  min="0"
                  value={montantDevise}
                  onChange={(e) => setMontantDevise(e.target.value)}
                  placeholder="120.00"
                  required={devisePresente}
                />
              </div>
            </div>
          </details>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="exp-team">Équipe</Label>
              <NativeSelect
                id="exp-team"
                value={team}
                onChange={(e) =>
                  setTeam(e.target.value === "" ? "" : Number(e.target.value))
                }
              >
                <option value="">—</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="exp-project">Projet</Label>
              <NativeSelect
                id="exp-project"
                value={project}
                onChange={(e) =>
                  setProject(e.target.value === "" ? "" : Number(e.target.value))
                }
              >
                <option value="">—</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="exp-beneficiary">Prospect / bénéficiaire</Label>
              <NativeSelect
                id="exp-beneficiary"
                value={beneficiary}
                onChange={(e) =>
                  setBeneficiary(e.target.value === "" ? "" : Number(e.target.value))
                }
              >
                <option value="">—</option>
                {beneficiaries.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="exp-payment">Mode de paiement</Label>
              <NativeSelect
                id="exp-payment"
                value={payment}
                onChange={(e) => setPayment(e.target.value)}
              >
                {Object.entries(PAYMENT_METHODS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="exp-description">Description</Label>
            <Textarea
              id="exp-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Annuler
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Enregistrer
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
