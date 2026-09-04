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
import { Textarea } from "@/components/ui/textarea"
import type {
  Beneficiary,
  Expense,
  ExpenseTitle,
  Manager,
  MarketingCategory,
  Project,
  Team,
} from "@/lib/types"
import {
  fromCountryLocalInput,
  normalizeDecimal,
  toCountryLocalInput,
} from "@/lib/utils"

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
  expenseTitles: ExpenseTitle[]
  marketingCategories: MarketingCategory[]
  managers: Manager[]
  currency: string
  /** Fuseau du pays : la date saisie est une heure de là-bas. */
  timezone: string
}

/**
 * Saisie d'une ligne de dépense.
 *
 * Le montant justifié n'y figure pas : le pays déclare, le siège constate.
 * C'est la transition « Marquer justifié » qui le fixe, et le serveur seul
 * calcule l'écart.
 */
export function ExpenseForm({ open, onOpenChange, editing, ...rest }: ExpenseFormProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        {/* Monté à l'ouverture seulement : l'état repart de la dépense
            éditée sans effet de réinitialisation. */}
        {open && (
          <ExpenseFormBody
            key={editing?.id ?? "nouvelle"}
            editing={editing}
            onOpenChange={onOpenChange}
            {...rest}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function ExpenseFormBody({
  onOpenChange,
  onSave,
  editing,
  teams,
  projects,
  beneficiaries,
  expenseTitles,
  marketingCategories,
  managers,
  currency,
  timezone,
}: Omit<ExpenseFormProps, "open">) {
  const [title, setTitle] = useState(editing?.title ?? "")
  const [date, setDate] = useState(
    toCountryLocalInput(editing?.date ?? new Date().toISOString(), timezone),
  )
  const [place, setPlace] = useState(editing?.place ?? "")
  const [amount, setAmount] = useState(editing?.amount ?? "")
  // Devise du décaissement : vide tant que la dépense est faite dans la
  // devise du pays, cas de très loin le plus fréquent.
  const [devise, setDevise] = useState(editing?.original_currency ?? "")
  const [montantDevise, setMontantDevise] = useState(editing?.original_amount ?? "")
  const [team, setTeam] = useState<number | "">(editing?.team ?? "")
  const [project, setProject] = useState<number | "">(editing?.project ?? "")
  const [owner, setOwner] = useState<number | "">(editing?.owner ?? "")
  const [expenseTitle, setExpenseTitle] = useState<number | "">(editing?.expense_title ?? "")
  const [category, setCategory] = useState<number | "">(editing?.marketing_category ?? "")
  const [beneficiary, setBeneficiary] = useState<number | "">(editing?.beneficiary ?? "")
  const [payment, setPayment] = useState(editing?.payment_method ?? "cash")
  const [description, setDescription] = useState(editing?.description ?? "")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // Le repli « autre devise » ne s'ouvre seul qu'à l'ouverture, si la dépense
  // en a une ; ensuite la personne reste maîtresse de l'ouvrir ou le fermer.
  const [deviseOuverte] = useState(Boolean(editing?.original_currency))

  const devisePresente = devise.trim() !== ""

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const instant = fromCountryLocalInput(date, timezone)
    if (!instant) {
      setError("Indiquez la date et l'heure de la dépense.")
      return
    }
    const enDeviseEtrangere = devisePresente && montantDevise.trim() !== ""
    const montant = enDeviseEtrangere ? null : normalizeDecimal(amount)
    if (!enDeviseEtrangere && montant === null) {
      setError("Indiquez le montant de la dépense, en chiffres.")
      return
    }
    const montantEtranger = enDeviseEtrangere ? normalizeDecimal(montantDevise) : null
    if (enDeviseEtrangere && montantEtranger === null) {
      setError("Indiquez le montant décaissé, en chiffres.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave({
        title,
        date: instant,
        place,
        // En devise étrangère, le serveur calcule le montant du pays : le lui
        // envoyer serait lui proposer un taux, ce qui n'est pas au pays d'en
        // décider.
        amount: enDeviseEtrangere ? undefined : montant,
        original_currency: enDeviseEtrangere ? devise.trim().toUpperCase() : "",
        original_amount: montantEtranger,
        team: team === "" ? null : team,
        project: project === "" ? null : project,
        owner: owner === "" ? null : owner,
        expense_title: expenseTitle === "" ? null : expenseTitle,
        marketing_category: category === "" ? null : category,
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

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {editing ? "Modifier la dépense" : "Ajouter une dépense"}
        </DialogTitle>
        <DialogDescription>
          Ce qui a été dépensé, quand, où et pour qui. Le siège constatera ce
          que les pièces justifient.
        </DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
        <FormError>{error}</FormError>

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
            <Label htmlFor="exp-date">Date et heure (heure de {timezone})</Label>
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
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              disabled={devisePresente}
              placeholder={devisePresente ? "converti par le serveur" : "12 500,00"}
              required={!devisePresente}
            />
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

        {/* Décaissement dans une autre devise (§5.3). Replié par défaut :
            la quasi-totalité des dépenses est faite dans la devise du pays,
            et deux champs de plus alourdiraient chaque saisie. */}
        <details
          className="rounded-lg border border-border/60 p-3"
          open={deviseOuverte || undefined}
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
                inputMode="decimal"
                value={montantDevise}
                onChange={(e) => setMontantDevise(e.target.value)}
                placeholder="120,00"
                required={devisePresente}
              />
            </div>
          </div>
        </details>

        <div className="grid grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label htmlFor="exp-expense-title">Intitulé de dépense</Label>
            <NativeSelect
              id="exp-expense-title"
              value={expenseTitle}
              onChange={(e) =>
                setExpenseTitle(e.target.value === "" ? "" : Number(e.target.value))
              }
            >
              <option value="">—</option>
              {expenseTitles.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="exp-category">Catégorie marketing</Label>
            <NativeSelect
              id="exp-category"
              value={category}
              onChange={(e) =>
                setCategory(e.target.value === "" ? "" : Number(e.target.value))
              }
            >
              <option value="">—</option>
              {marketingCategories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </NativeSelect>
          </div>
        </div>

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
            <Label htmlFor="exp-owner">Manager responsable</Label>
            <NativeSelect
              id="exp-owner"
              value={owner}
              onChange={(e) =>
                setOwner(e.target.value === "" ? "" : Number(e.target.value))
              }
            >
              <option value="">—</option>
              {managers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </NativeSelect>
          </div>
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
    </>
  )
}
