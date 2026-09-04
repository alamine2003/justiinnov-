import { useState, type FormEvent } from "react"
import { AlertTriangle, Loader2, Pencil, Plus, ShieldOff, Users } from "lucide-react"
import { useTranslation } from "react-i18next"
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
import {
  createUser,
  fetchPermissionMatrix,
  fetchUsers,
  resetTwoFactor,
  updateUser,
} from "@/lib/accounts"
import { useAuth } from "@/context/use-auth"
import { fetchCountries } from "@/lib/countries"
import { ROLES, roleLabel } from "@/lib/labels"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import { STATUS_TONES } from "@/lib/status-styles"
import {
  type AccountUser,
  type CountrySummary,
  type PermissionMatrix,
  type Role,
} from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn } from "@/lib/utils"

export function UsersSection() {
  const { t } = useTranslation()
  const { me } = useAuth()
  const [page, setPage] = useState(1)
  const [actionError, setActionError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [toggling, setToggling] = useState<number | null>(null)
  const [editing, setEditing] = useState<AccountUser | null>(null)
  const [resetting, setResetting] = useState<AccountUser | null>(null)

  const query = useQuery(
    `users:${page}`,
    (signal) => fetchUsers({ page, page_size: PAGE_SIZE }, signal),
    { fallback: t("configuration.utilisateurs.chargement_impossible") },
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
      setActionError(
        e instanceof Error ? e.message : t("configuration.utilisateurs.statut_impossible"),
      )
    } finally {
      setToggling(null)
    }
  }

  const error = actionError ?? query.error ?? countries.error ?? matrix.error

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">{t("configuration.utilisateurs.titre")}</h2>
          <p className="text-xs text-muted-foreground">
            {t("configuration.utilisateurs.description")}
          </p>
        </div>
        <Button
          onClick={() => {
            setEditing(null)
            setFormOpen(true)
          }}
        >
          <Plus className="mr-2 h-4 w-4" aria-hidden />
          {t("configuration.utilisateurs.creer")}
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={countries.data} noun={t("configuration.pays.noun_pluriel")} />

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">{t("champs.username")}</TableHead>
                  <TableHead scope="col">{t("commun.nom")}</TableHead>
                  <TableHead scope="col">{t("champs.role")}</TableHead>
                  <TableHead scope="col">{t("configuration.utilisateurs.perimetre")}</TableHead>
                  <TableHead scope="col">{t("commun.statut")}</TableHead>
                  <TableHead scope="col" className="text-right">
                    {t("commun.actions")}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={6} />
                ) : users.length === 0 ? (
                  <EmptyRow
                    colSpan={6}
                    icon={Users}
                    title={t("configuration.utilisateurs.vide_titre")}
                    hint={t("configuration.utilisateurs.vide_aide")}
                  />
                ) : (
                  users.map((user) => {
                    const self = user.id === me?.id
                    return (
                      <TableRow key={user.id}>
                        <TableCell className="font-medium">{user.username}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {[user.first_name, user.last_name].filter(Boolean).join(" ") ||
                            t("commun.aucun")}
                        </TableCell>
                        <TableCell>
                          {user.role ? (
                            <Badge variant="secondary">
                              {matrix.data?.roles.find((r) => r.value === user.role)?.label ??
                                roleLabel(t, user.role)}
                            </Badge>
                          ) : (
                            <Badge variant="outline">{t("commun.sans_role")}</Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {user.countries_detail.length > 0
                            ? user.countries_detail
                                .map((c) => c.country_ref ?? c.name)
                                .join(", ")
                            : user.role
                              ? t("commun.siege_tous_pays")
                              : t("commun.aucun")}
                        </TableCell>
                        <TableCell>
                          {user.is_active ? (
                            <Badge className={STATUS_TONES.SUCCES}>{t("commun.actif")}</Badge>
                          ) : (
                            <Badge variant="secondary">{t("commun.desactive")}</Badge>
                          )}
                          {user.must_change_password && (
                            <Badge variant="outline" className="ml-1">
                              {t("configuration.utilisateurs.mdp_provisoire")}
                            </Badge>
                          )}
                          {/* Absent sur un serveur qui ne connaît pas la 2FA :
                              on ne prétend alors rien. */}
                          {user.totp_confirmed === true && (
                            <Badge className={cn("ml-1", STATUS_TONES.SUCCES)}>
                              {t("configuration.utilisateurs.totp_active")}
                            </Badge>
                          )}
                          {user.totp_confirmed === false && (
                            <Badge className={cn("ml-1", STATUS_TONES.ATTENTE)}>
                              {t("configuration.utilisateurs.totp_a_enroler")}
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            {/* Un bouton désactivé ne porte pas d'infobulle
                                lisible : l'explication est à côté. */}
                            {self && (
                              <span className="text-xs text-muted-foreground">
                                {t("configuration.utilisateurs.soi_meme")}
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
                              {user.is_active ? t("commun.desactiver") : t("commun.activer")}
                            </Button>
                            {user.totp_confirmed === true && (
                              <Button
                                variant="ghost"
                                size="icon"
                                aria-label={t("configuration.utilisateurs.totp_reinitialiser_aria", {
                                  nom: user.username,
                                })}
                                onClick={() => setResetting(user)}
                              >
                                <ShieldOff className="h-4 w-4" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={t("configuration.utilisateurs.modifier_aria", {
                                nom: user.username,
                              })}
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
            noun={[
              t("configuration.utilisateurs.noun_singulier"),
              t("configuration.utilisateurs.noun_pluriel"),
            ]}
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

      {resetting && (
        <ResetTwoFactorDialog
          user={resetting}
          onOpenChange={(open) => {
            if (!open) setResetting(null)
          }}
          onDone={() => query.reload()}
        />
      )}
    </div>
  )
}

/**
 * Confirmation avant de réinitialiser l'enrôlement : le titulaire perdra
 * l'accès jusqu'à ce qu'il ait lié à nouveau son application, et l'action
 * est inscrite au journal.
 */
function ResetTwoFactorDialog({
  user,
  onOpenChange,
  onDone,
}: {
  user: AccountUser
  onOpenChange: (open: boolean) => void
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const confirmer = async () => {
    setSaving(true)
    setError(null)
    try {
      await resetTwoFactor(user.id)
      onDone()
      onOpenChange(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : t("configuration.utilisateurs.totp_reinit_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t("configuration.utilisateurs.totp_reinit_titre", { nom: user.username })}
          </DialogTitle>
          <DialogDescription>
            {t("configuration.utilisateurs.totp_reinit_description")}
          </DialogDescription>
        </DialogHeader>
        <FormError>{error}</FormError>
        <DialogFooter>
          <div>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("commun.annuler")}
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={saving}
              className="ml-2"
              onClick={() => void confirmer()}
            >
              {saving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ShieldOff className="mr-2 h-4 w-4" aria-hidden />
              )}
              {t("configuration.utilisateurs.totp_reinitialiser")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
  const { t } = useTranslation()
  const roles = matrix?.roles ?? []
  const [username, setUsername] = useState(editing?.username ?? "")
  const [firstName, setFirstName] = useState(editing?.first_name ?? "")
  const [lastName, setLastName] = useState(editing?.last_name ?? "")
  const [email, setEmail] = useState(editing?.email ?? "")
  // Le compte le plus courant est celui d'un manager de pays.
  const [role, setRole] = useState<Role | "">(editing?.role ?? "manager")
  const [countryIds, setCountryIds] = useState<number[]>(editing?.countries ?? [])
  // Le périmètre n'est envoyé que s'il a été touché : un PATCH qui renvoie
  // la liste telle quelle réécrit une trace de changement pour rien.
  const [countriesTouched, setCountriesTouched] = useState(false)
  const [password, setPassword] = useState("")
  const [active, setActive] = useState(editing?.is_active ?? true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Le rattachement au siège vient du serveur. Tant que la matrice n'est pas
  // chargée, il reste inconnu : le formulaire propose alors les rôles sans
  // annoncer leur périmètre et laisse le serveur trancher, plutôt que de
  // recopier ici une table de rôles qui divergerait. Un compte du siège
  // sans pays voit tous les pays ; des pays cochés restreignent un DM ou
  // un DF — le serveur refuse une restriction à un rôle toujours global.
  const roleInfo = roles.find((r) => r.value === role)
  const isHeadquarters = Boolean(roleInfo?.siege)

  const toggleCountry = (id: number, checked: boolean) => {
    setCountriesTouched(true)
    setCountryIds((current) =>
      checked ? [...new Set([...current, id])] : current.filter((c) => c !== id),
    )
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!role) {
      setError(t("configuration.utilisateurs.form.role_requis"))
      return
    }
    if (roleInfo && !isHeadquarters && countryIds.length === 0) {
      setError(t("configuration.utilisateurs.form.pays_requis"))
      return
    }
    // L'adresse nomme le compte dans l'application d'authentification et
    // reçoit les notifications ; le serveur en vérifie le domaine.
    if (!email.trim()) {
      setError(t("configuration.utilisateurs.form.email_requis"))
      return
    }
    if (!editing && !password) {
      setError(t("configuration.utilisateurs.form.mdp_requis"))
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
      // Vide, le périmètre d'un compte du siège vaut tous les pays. Un
      // changement de rôle renvoie le périmètre tel qu'affiché, pour que
      // le serveur le revalide contre le nouveau rôle.
      if (!editing || countriesTouched || role !== editing.role) {
        payload.countries = countryIds
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
      setError(err instanceof Error ? err.message : t("erreurs.enregistrement_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editing
              ? t("configuration.utilisateurs.form.titre_modifier")
              : t("configuration.utilisateurs.form.titre_creer")}
          </DialogTitle>
          <DialogDescription>
            {t("configuration.utilisateurs.form.description")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>

          <div className="grid gap-2">
            <Label htmlFor="user-username">{t("champs.username")}</Label>
            <Input
              id="user-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("configuration.utilisateurs.form.identifiant_exemple")}
              autoComplete="off"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="user-first">{t("configuration.utilisateurs.form.prenom")}</Label>
              <Input
                id="user-first"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="user-last">{t("commun.nom")}</Label>
              <Input
                id="user-last"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="user-email">{t("champs.email")}</Label>
            <Input
              id="user-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("configuration.utilisateurs.form.email_exemple")}
              autoComplete="off"
              required
            />
            <p className="text-xs text-muted-foreground">
              {t("configuration.utilisateurs.form.email_aide")}
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="user-role">{t("champs.role")}</Label>
            <NativeSelect
              id="user-role"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              required
            >
              {roles.length > 0
                ? roles.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.siege
                        ? t("configuration.utilisateurs.form.role_siege", { role: r.label })
                        : t("configuration.utilisateurs.form.role_pays", { role: r.label })}
                    </option>
                  ))
                : ROLES.map((value) => (
                    <option key={value} value={value}>
                      {roleLabel(t, value)}
                    </option>
                  ))}
            </NativeSelect>
            <p className="text-xs text-muted-foreground">
              {t("configuration.utilisateurs.form.role_aide")}
            </p>
          </div>

          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium">
              {t("configuration.utilisateurs.form.perimetre_legend")}
            </legend>
            <p className="text-xs text-muted-foreground">
              {isHeadquarters
                ? t("configuration.utilisateurs.form.perimetre_aide_siege")
                : t("configuration.utilisateurs.form.perimetre_aide_pays")}
            </p>
            <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border/60 p-2">
              {countries.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  {t("configuration.utilisateurs.form.aucun_pays")}
                </p>
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
          </fieldset>

          <div className="grid gap-2">
            <Label htmlFor="user-password">
              {editing
                ? t("configuration.utilisateurs.form.mot_de_passe_optionnel")
                : t("configuration.utilisateurs.form.mot_de_passe")}
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
            <Label htmlFor="user-active" className="text-sm">
              {t("configuration.utilisateurs.form.compte_actif")}
            </Label>
            <Switch id="user-active" checked={active} onCheckedChange={setActive} />
          </div>

          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("commun.enregistrer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
