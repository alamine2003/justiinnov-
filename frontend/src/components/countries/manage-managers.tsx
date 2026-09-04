import { useState, type FormEvent } from "react"
import { Link2, Loader2, Pencil, Plus, Unlink, Users } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
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
import { Switch } from "@/components/ui/switch"
import { EmptyRow } from "@/components/ui/table-states"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  createManager,
  updateCountryManagers,
  updateManager,
} from "@/lib/countries"
import { STATUS_TONES } from "@/lib/status-styles"
import type { Manager } from "@/lib/types"

interface ManageManagersProps {
  countryId: number
  managers: Manager[]
  onRefresh: () => void | Promise<void>
  /** Le référentiel des managers relève du siège. */
  canManage: boolean
}

export function ManageManagers({
  countryId,
  managers,
  onRefresh,
  canManage,
}: ManageManagersProps) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState<Manager | null | "nouveau">(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleDetach = async (manager: Manager) => {
    setBusyId(manager.id)
    setError(null)
    try {
      await updateCountryManagers(
        countryId,
        managers.filter((m) => m.id !== manager.id).map((m) => m.id),
      )
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : t("pays.managers.retrait_impossible"))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t("pays.managers.titre")}</h3>
          <p className="text-xs text-muted-foreground">{t("pays.managers.description")}</p>
        </div>
        {canManage && (
          <Button size="sm" onClick={() => setEditing("nouveau")}>
            <Plus className="mr-1 h-4 w-4" aria-hidden />
            {t("commun.ajouter")}
          </Button>
        )}
      </div>

      <FormError>{error}</FormError>

      <div className="overflow-x-auto rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">{t("champs.manager")}</TableHead>
              <TableHead scope="col">{t("champs.email")}</TableHead>
              <TableHead scope="col">{t("pays.managers.fonction")}</TableHead>
              <TableHead scope="col">{t("commun.statut")}</TableHead>
              <TableHead scope="col" className="text-right">{t("commun.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {managers.length === 0 ? (
              <EmptyRow
                colSpan={5}
                icon={Users}
                title={t("pays.managers.vide_titre")}
                hint={
                  canManage
                    ? t("pays.managers.vide_indice_gestion")
                    : t("pays.managers.vide_indice")
                }
              />
            ) : (
              managers.map((manager) => (
                <TableRow key={manager.id}>
                  <TableCell>
                    <span className="font-medium">{manager.name}</span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {manager.email || (
                      <span className="text-muted-foreground/60">{t("commun.aucun")}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {manager.title || (
                      <span className="text-muted-foreground/60">{t("commun.aucun")}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {manager.is_active ? (
                      <Badge className={STATUS_TONES.SUCCES}>{t("pays.statut.actif")}</Badge>
                    ) : (
                      <Badge variant="secondary">{t("pays.statut.inactif")}</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {canManage ? (
                      <>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setEditing(manager)}
                          aria-label={t("pays.managers.modifier_aria", { nom: manager.name })}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => void handleDetach(manager)}
                          aria-label={t("pays.managers.retirer_aria", { nom: manager.name })}
                          disabled={busyId === manager.id}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          {busyId === manager.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Unlink className="h-4 w-4" />
                          )}
                        </Button>
                      </>
                    ) : (
                      <span className="text-muted-foreground">{t("commun.aucun")}</span>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {editing !== null && (
        <ManagerDialog
          key={editing === "nouveau" ? "nouveau" : editing.id}
          manager={editing === "nouveau" ? null : editing}
          countryId={countryId}
          managers={managers}
          onClose={() => setEditing(null)}
          onSaved={onRefresh}
        />
      )}
    </div>
  )
}

function ManagerDialog({
  manager,
  countryId,
  managers,
  onClose,
  onSaved,
}: {
  manager: Manager | null
  countryId: number
  managers: Manager[]
  onClose: () => void
  onSaved: () => void | Promise<void>
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(manager?.name ?? "")
  const [email, setEmail] = useState(manager?.email ?? "")
  const [title, setTitle] = useState(manager?.title ?? "")
  const [active, setActive] = useState(manager?.is_active ?? true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = { name, email, title, is_active: active }
      if (manager) {
        await updateManager(manager.id, payload)
      } else {
        const created = await createManager(payload)
        await updateCountryManagers(countryId, [
          ...managers.map((m) => m.id),
          created.id,
        ])
      }
      await onSaved()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : t("erreurs.enregistrement_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="h-4 w-4" aria-hidden />
            {manager
              ? t("pays.managers.dialogue_modifier")
              : t("pays.managers.dialogue_ajouter")}
          </DialogTitle>
          <DialogDescription>
            {manager ? t("pays.managers.aide_modifier") : t("pays.managers.aide_ajouter")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="m-name">{t("champs.name")}</Label>
            <Input
              id="m-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("pays.managers.nom_placeholder")}
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="m-email">{t("champs.email")}</Label>
            <Input
              id="m-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("pays.managers.email_placeholder")}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="m-title">{t("pays.managers.fonction")}</Label>
            <Input
              id="m-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("pays.managers.fonction_placeholder")}
            />
          </div>
          <div className="flex items-center justify-between rounded-lg border p-3">
            <Label htmlFor="m-active" className="text-sm">{t("commun.actif")}</Label>
            <Switch id="m-active" checked={active} onCheckedChange={setActive} />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={onClose}>
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
