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
import {
  OVERRUN_POLICY_LABELS,
  type Budget,
  type CountrySummary,
  type Manager,
  type OverrunPolicy,
  type Project,
  type Team,
} from "@/lib/types"

export interface BudgetFormValues {
  country: number
  year: number
  project: number | null
  team: number | null
  manager: number | null
  amount: string
  overrun_policy: OverrunPolicy
  is_active: boolean
}

/** Dimensions selon lesquelles une enveloppe pays peut être découpée (§5.2). */
const SCOPES = [
  { value: "country", label: "Enveloppe du pays" },
  { value: "project", label: "Sous-enveloppe — projet" },
  { value: "team", label: "Sous-enveloppe — équipe" },
  { value: "manager", label: "Sous-enveloppe — manager" },
] as const

type Scope = (typeof SCOPES)[number]["value"]

interface BudgetFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (values: BudgetFormValues) => Promise<void>
  countries: CountrySummary[]
  projects: Project[]
  teams: Team[]
  managers: Manager[]
  editing: Budget | null
}

const CURRENT_YEAR = new Date().getFullYear()
const YEARS = [CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1, CURRENT_YEAR + 2]

export function BudgetForm({
  open,
  onOpenChange,
  onSave,
  countries,
  projects,
  teams,
  managers,
  editing,
}: BudgetFormProps) {
  const [country, setCountry] = useState<number | "">("")
  const [year, setYear] = useState(CURRENT_YEAR)
  const [scope, setScope] = useState<Scope>("country")
  const [project, setProject] = useState<number | "">("")
  const [team, setTeam] = useState<number | "">("")
  const [manager, setManager] = useState<number | "">("")
  const [amount, setAmount] = useState("")
  const [policy, setPolicy] = useState<OverrunPolicy>("block")
  const [active, setActive] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setError(null)
    if (editing) {
      setCountry(editing.country)
      setYear(editing.year)
      setScope(editing.scope_kind)
      setProject(editing.project ?? "")
      setTeam(editing.team ?? "")
      setManager(editing.manager ?? "")
      setAmount(editing.amount)
      setPolicy(editing.overrun_policy)
      setActive(editing.is_active)
    } else {
      setCountry(countries[0]?.id ?? "")
      setYear(CURRENT_YEAR)
      setScope("country")
      setProject("")
      setTeam("")
      setManager("")
      setAmount("")
      setPolicy("block")
      setActive(true)
    }
  }, [open, editing, countries])

  // Une sous-enveloppe ne porte que sur une entité du pays choisi.
  const eligibleProjects = projects.filter((p) => p.country === country)
  const eligibleTeams = teams.filter((t) => t.country === country)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (country === "") {
      setError("Sélectionnez un pays.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave({
        country,
        year,
        // Une seule dimension est transmise : les autres sont explicitement
        // nulles, sans quoi une modification de portée en laisserait traîner.
        project: scope === "project" && project !== "" ? project : null,
        team: scope === "team" && team !== "" ? team : null,
        manager: scope === "manager" && manager !== "" ? manager : null,
        amount,
        overrun_policy: policy,
        is_active: active,
      })
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enregistrement impossible")
    } finally {
      setSaving(false)
    }
  }

  const selectedCountry = countries.find((c) => c.id === country)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {editing ? "Modifier l'enveloppe" : "Attribuer une enveloppe"}
          </DialogTitle>
          <DialogDescription>
            Une sous-enveloppe découpe l'enveloppe du pays selon une seule
            dimension : un projet, une équipe ou un manager.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2">
          {error && (
            <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}

          <div className="grid gap-2">
            <Label htmlFor="budget-country">Pays</Label>
            <NativeSelect
              id="budget-country"
              value={country}
              onChange={(e) => {
                setCountry(Number(e.target.value))
                setProject("")
              }}
              disabled={Boolean(editing)}
            >
              {countries.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.country_ref ? `${c.country_ref} — ` : ""}
                  {c.name}
                </option>
              ))}
            </NativeSelect>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="budget-year">Année</Label>
              <NativeSelect
                id="budget-year"
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
                disabled={Boolean(editing)}
              >
                {YEARS.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="budget-amount">
                Montant {selectedCountry ? `(${selectedCountry.currency})` : ""}
              </Label>
              <Input
                id="budget-amount"
                type="number"
                step="0.01"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="10000000"
                required
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="budget-scope">Portée</Label>
            <NativeSelect
              id="budget-scope"
              value={scope}
              onChange={(e) => setScope(e.target.value as Scope)}
              disabled={Boolean(editing)}
            >
              {SCOPES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </NativeSelect>
          </div>

          {scope === "project" && (
            <div className="grid gap-2">
              <Label htmlFor="budget-project">Projet</Label>
              <NativeSelect
                id="budget-project"
                value={project}
                onChange={(e) =>
                  setProject(e.target.value === "" ? "" : Number(e.target.value))
                }
                disabled={Boolean(editing)}
                required
              >
                <option value="">—</option>
                {eligibleProjects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}

          {scope === "team" && (
            <div className="grid gap-2">
              <Label htmlFor="budget-team">Équipe</Label>
              <NativeSelect
                id="budget-team"
                value={team}
                onChange={(e) =>
                  setTeam(e.target.value === "" ? "" : Number(e.target.value))
                }
                disabled={Boolean(editing)}
                required
              >
                <option value="">—</option>
                {eligibleTeams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}

          {scope === "manager" && (
            <div className="grid gap-2">
              <Label htmlFor="budget-manager">Manager</Label>
              <NativeSelect
                id="budget-manager"
                value={manager}
                onChange={(e) =>
                  setManager(e.target.value === "" ? "" : Number(e.target.value))
                }
                disabled={Boolean(editing)}
                required
              >
                <option value="">—</option>
                {managers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="budget-policy">En cas de dépassement</Label>
            <NativeSelect
              id="budget-policy"
              value={policy}
              onChange={(e) => setPolicy(e.target.value as OverrunPolicy)}
            >
              {Object.entries(OVERRUN_POLICY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </div>

          <div className="flex items-center justify-between rounded-lg border p-3">
            <p className="text-sm">Active</p>
            <Switch checked={active} onCheckedChange={setActive} />
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
