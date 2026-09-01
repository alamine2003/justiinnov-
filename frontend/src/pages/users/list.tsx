import { useCallback, useEffect, useState, type FormEvent } from "react"
import { AlertTriangle, Loader2, Pencil, Plus } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { createUser, fetchUsers, updateUser } from "@/lib/accounts"
import { fetchCountries } from "@/lib/countries"
import { ROLE_LABELS, type AccountUser, type CountrySummary, type Role } from "@/lib/types"

/** Rôles exercés depuis le siège : leur périmètre couvre tous les pays. */
const HEADQUARTERS_ROLES: Role[] = [
  "super_admin",
  "admin",
  "doo",
  "controller",
  "auditor",
]

export function UsersPage() {
  const [users, setUsers] = useState<AccountUser[]>([])
  const [countries, setCountries] = useState<CountrySummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<AccountUser | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [userPage, countryPage] = await Promise.all([
        fetchUsers({ page_size: 200 }),
        fetchCountries({ page_size: 200 }),
      ])
      setUsers(userPage.results)
      setCountries(countryPage.results)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger les comptes")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Comptes</h1>
          <p className="text-sm text-muted-foreground">
            Rôles et périmètres pays. Un compte du siège voit tous les pays ; un
            responsable pays ne voit que le sien.
          </p>
        </div>
        <Button
          onClick={() => {
            setEditing(null)
            setFormOpen(true)
          }}
        >
          <Plus className="mr-2 h-4 w-4" />
          Créer un compte
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <div className="overflow-hidden rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Identifiant</TableHead>
                  <TableHead>Nom</TableHead>
                  <TableHead>Rôle</TableHead>
                  <TableHead>Périmètre</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={6} className="h-16">
                      <div className="h-4 animate-pulse rounded bg-muted" />
                    </TableCell>
                  </TableRow>
                ) : users.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                      Aucun compte.
                    </TableCell>
                  </TableRow>
                ) : (
                  users.map((user) => (
                    <TableRow key={user.id}>
                      <TableCell className="font-medium">{user.username}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {[user.first_name, user.last_name].filter(Boolean).join(" ") || "—"}
                      </TableCell>
                      <TableCell>
                        {user.role ? (
                          <Badge variant="secondary">{ROLE_LABELS[user.role]}</Badge>
                        ) : (
                          <Badge variant="outline">Sans rôle</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {user.countries_detail.length > 0
                          ? user.countries_detail
                              .map((c) => c.country_ref ?? c.name)
                              .join(", ")
                          : user.role
                            ? "Siège — tous pays"
                            : "—"}
                      </TableCell>
                      <TableCell>
                        {user.is_active ? (
                          <Badge className="bg-emerald-500 hover:bg-emerald-500">Actif</Badge>
                        ) : (
                          <Badge variant="secondary">Désactivé</Badge>
                        )}
                        {user.must_change_password && (
                          <Badge variant="outline" className="ml-1">
                            mot de passe provisoire
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Modifier"
                          onClick={() => {
                            setEditing(user)
                            setFormOpen(true)
                          }}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <UserForm
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open)
          if (!open) setEditing(null)
        }}
        countries={countries}
        editing={editing}
        onSaved={load}
      />
    </div>
  )
}

function UserForm({
  open,
  onOpenChange,
  countries,
  editing,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  countries: CountrySummary[]
  editing: AccountUser | null
  onSaved: () => Promise<void>
}) {
  const [username, setUsername] = useState("")
  const [firstName, setFirstName] = useState("")
  const [lastName, setLastName] = useState("")
  const [email, setEmail] = useState("")
  const [role, setRole] = useState<Role>("country_manager")
  const [countryId, setCountryId] = useState<number | "">("")
  const [password, setPassword] = useState("")
  const [active, setActive] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setError(null)
    setPassword("")
    if (editing) {
      setUsername(editing.username)
      setFirstName(editing.first_name)
      setLastName(editing.last_name)
      setEmail(editing.email)
      setRole(editing.role ?? "country_manager")
      setCountryId(editing.countries[0] ?? "")
      setActive(editing.is_active)
    } else {
      setUsername("")
      setFirstName("")
      setLastName("")
      setEmail("")
      setRole("country_manager")
      setCountryId(countries[0]?.id ?? "")
      setActive(true)
    }
  }, [open, editing, countries])

  const isHeadquarters = HEADQUARTERS_ROLES.includes(role)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload: Record<string, unknown> = {
        username,
        first_name: firstName,
        last_name: lastName,
        email,
        role,
        is_active: active,
        // Un rôle du siège n'a pas de périmètre : c'est ce qui lui donne
        // accès à tous les pays.
        countries: isHeadquarters || countryId === "" ? [] : [countryId],
      }
      if (password) payload.password = password

      if (editing) {
        await updateUser(editing.id, payload)
      } else {
        await createUser(payload)
      }
      await onSaved()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enregistrement impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editing ? "Modifier le compte" : "Créer un compte"}</DialogTitle>
          <DialogDescription>
            Le mot de passe défini ici est provisoire : son titulaire sera invité
            à le remplacer.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2">
          {error && (
            <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}

          <div className="grid gap-2">
            <Label htmlFor="user-username">Identifiant</Label>
            <Input
              id="user-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="pays.innov"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="user-first">Prénom</Label>
              <Input
                id="user-first"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="user-last">Nom</Label>
              <Input
                id="user-last"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="user-email">Email</Label>
            <Input
              id="user-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="user-role">Rôle</Label>
            <NativeSelect
              id="user-role"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
            >
              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="user-country">Pays</Label>
            <NativeSelect
              id="user-country"
              value={isHeadquarters ? "" : countryId}
              onChange={(e) =>
                setCountryId(e.target.value === "" ? "" : Number(e.target.value))
              }
              disabled={isHeadquarters}
            >
              {isHeadquarters ? (
                <option value="">Siège — tous les pays</option>
              ) : (
                countries.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.country_ref ? `${c.country_ref} — ` : ""}
                    {c.name}
                  </option>
                ))
              )}
            </NativeSelect>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="user-password">
              Mot de passe {editing && "(laisser vide pour ne pas changer)"}
            </Label>
            <Input
              id="user-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required={!editing}
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border p-3">
            <p className="text-sm">Compte actif</p>
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
