import { useState, type FormEvent } from "react"
import { AlertTriangle, Loader2, Pencil, Plus, Users } from "lucide-react"
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
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { createUser, fetchPermissionMatrix, fetchUsers, updateUser } from "@/lib/accounts"
import { useAuth } from "@/context/use-auth"
import { fetchCountries } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import { STATUS_TONES } from "@/lib/status-styles"
import {
  ROLE_LABELS,
  type AccountUser,
  type CountrySummary,
  type PermissionMatrix,
  type Role,
} from "@/lib/types"
import { useQuery } from "@/lib/use-query"

export function UsersSection() {
  const { me } = useAuth()
  const [page, setPage] = useState(1)
  const [actionError, setActionError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [toggling, setToggling] = useState<number | null>(null)
  const [editing, setEditing] = useState<AccountUser | null>(null)

  const query = useQuery(
    `users:${page}`,
    (signal) => fetchUsers({ page, page_size: PAGE_SIZE }, signal),
    { fallback: "Impossible de charger les comptes" },
  )
  const countries = useReferentiel("countries", () =>
    fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
  )
  // Les rôles et leur rattachement au siège viennent du serveur : recopier
  // la liste ici la ferait diverger au premier rôle ajouté.
  const matrix = useReferentiel("permissions", fetchPermissionMatrix)

  const users = query.data?.results ?? []

  // Le siège ne peut pas se désactiver lui-même : le backend le refuse aussi,
  // le bouton grisé évite simplement d'aller au-devant d'une erreur.
  const toggle = async (user: AccountUser) => {
    setToggling(user.id)
    setActionError(null)
    try {
      await updateUser(user.id, { is_active: !user.is_active })
      query.reload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Changement de statut impossible")
    } finally {
      setToggling(null)
    }
  }

  const error = actionError ?? query.error ?? countries.error ?? matrix.error

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">Comptes</h2>
          <p className="text-xs text-muted-foreground">
            Rôles et périmètres. Un compte du siège voit tous les pays ; un
            responsable pays ne voit que les siens.
          </p>
        </div>
        <Button
          onClick={() => {
            setEditing(null)
            setFormOpen(true)
          }}
        >
          <Plus className="mr-2 h-4 w-4" aria-hidden />
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
      <TruncatedNotice page={countries.data} noun="pays" />

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Identifiant</TableHead>
                  <TableHead scope="col">Nom</TableHead>
                  <TableHead scope="col">Rôle</TableHead>
                  <TableHead scope="col">Périmètre</TableHead>
                  <TableHead scope="col">Statut</TableHead>
                  <TableHead scope="col" className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={6} />
                ) : users.length === 0 ? (
                  <EmptyRow
                    colSpan={6}
                    icon={Users}
                    title="Aucun compte"
                    hint="Créez les comptes des représentants pays."
                  />
                ) : (
                  users.map((user) => {
                    const self = user.id === me?.id
                    return (
                      <TableRow key={user.id}>
                        <TableCell className="font-medium">{user.username}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {[user.first_name, user.last_name].filter(Boolean).join(" ") || "—"}
                        </TableCell>
                        <TableCell>
                          {user.role ? (
                            <Badge variant="secondary">
                              {matrix.data?.roles.find((r) => r.value === user.role)?.label ??
                                ROLE_LABELS[user.role]}
                            </Badge>
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
                            <Badge className={STATUS_TONES.SUCCES}>Actif</Badge>
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
                          <div className="flex items-center justify-end gap-1">
                            {/* Un bouton désactivé ne porte pas d'infobulle
                                lisible : l'explication est à côté. */}
                            {self && (
                              <span className="text-xs text-muted-foreground">
                                Un autre administrateur doit s'en charger.
                              </span>
                            )}
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={self || toggling === user.id}
                              onClick={() => void toggle(user)}
                            >
                              {toggling === user.id ? (
                                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                              ) : null}
                              {user.is_active ? "Désactiver" : "Activer"}
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Modifier ${user.username}`}
                              onClick={() => {
                                setEditing(user)
                                setFormOpen(true)
                              }}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>

          <Pagination
            page={page}
            count={query.data?.count ?? 0}
            onChange={setPage}
            noun={["compte", "comptes"]}
          />
        </CardContent>
      </Card>

      {formOpen && (
        <UserForm
          key={editing?.id ?? "nouveau"}
          onOpenChange={(open) => {
            setFormOpen(open)
            if (!open) setEditing(null)
          }}
          countries={countries.data?.results ?? []}
          matrix={matrix.data}
          editing={editing}
          onSaved={async () => {
            query.reload()
          }}
        />
      )}
    </div>
  )
}

function UserForm({
  onOpenChange,
  countries,
  matrix,
  editing,
  onSaved,
}: {
  onOpenChange: (open: boolean) => void
  countries: CountrySummary[]
  matrix: PermissionMatrix | null
  editing: AccountUser | null
  onSaved: () => Promise<void>
}) {
  const roles = matrix?.roles ?? []
  const [username, setUsername] = useState(editing?.username ?? "")
  const [firstName, setFirstName] = useState(editing?.first_name ?? "")
  const [lastName, setLastName] = useState(editing?.last_name ?? "")
  const [email, setEmail] = useState(editing?.email ?? "")
  const [role, setRole] = useState<Role | "">(editing?.role ?? "country_manager")
  const [countryIds, setCountryIds] = useState<number[]>(editing?.countries ?? [])
  // Le périmètre n'est envoyé que s'il a été touché : un PATCH qui renvoie
  // la liste telle quelle réécrit une trace de changement pour rien.
  const [countriesTouched, setCountriesTouched] = useState(false)
  const [password, setPassword] = useState("")
  const [active, setActive] = useState(editing?.is_active ?? true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const isHeadquarters = Boolean(roles.find((r) => r.value === role)?.siege)

  const toggleCountry = (id: number, checked: boolean) => {
    setCountriesTouched(true)
    setCountryIds((current) =>
      checked ? [...new Set([...current, id])] : current.filter((c) => c !== id),
    )
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!role) {
      setError("Choisissez un rôle.")
      return
    }
    if (!isHeadquarters && countryIds.length === 0) {
      setError("Un rôle pays doit être rattaché à au moins un pays.")
      return
    }
    if (!editing && !password) {
      setError("Un mot de passe provisoire est nécessaire à la création.")
      return
    }
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
      }
      // Un rôle du siège n'a pas de périmètre : c'est ce qui lui donne accès
      // à tous les pays.
      if (!editing || countriesTouched || isHeadquarters !== Boolean(editing.countries.length === 0)) {
        payload.countries = isHeadquarters ? [] : countryIds
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
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{editing ? "Modifier le compte" : "Créer un compte"}</DialogTitle>
          <DialogDescription>
            Le mot de passe défini ici est provisoire : son titulaire sera invité
            à le remplacer.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>

          <div className="grid gap-2">
            <Label htmlFor="user-username">Identifiant</Label>
            <Input
              id="user-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="pays.innov"
              autoComplete="off"
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
              disabled={roles.length === 0}
              required
            >
              {roles.length === 0 && <option value="">Rôles indisponibles</option>}
              {roles.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label} — {r.siege ? "siège" : "pays"}
                </option>
              ))}
            </NativeSelect>
          </div>

          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium">Pays du périmètre</legend>
            {isHeadquarters ? (
              <p className="text-xs text-muted-foreground">
                Rôle du siège : accès à tous les pays, sans rattachement.
              </p>
            ) : (
              <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border/60 p-2">
                {countries.length === 0 && (
                  <p className="text-xs text-muted-foreground">Aucun pays actif.</p>
                )}
                {countries.map((c) => (
                  <label
                    key={c.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-accent"
                  >
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-primary"
                      checked={countryIds.includes(c.id)}
                      onChange={(e) => toggleCountry(c.id, e.target.checked)}
                    />
                    {c.country_ref ? `${c.country_ref} — ` : ""}
                    {c.name}
                  </label>
                ))}
              </div>
            )}
          </fieldset>

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
            <Label htmlFor="user-active" className="text-sm">Compte actif</Label>
            <Switch id="user-active" checked={active} onCheckedChange={setActive} />
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
