import { useState, type FormEvent } from "react"
import { Link2, Loader2, Pencil, Plus, Unlink, Users } from "lucide-react"
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
      setError(e instanceof Error ? e.message : "Retrait impossible")
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Manager(s)</h3>
          <p className="text-xs text-muted-foreground">
            Responsables rattachés à ce pays.
          </p>
        </div>
        {canManage && (
          <Button size="sm" onClick={() => setEditing("nouveau")}>
            <Plus className="mr-1 h-4 w-4" aria-hidden />
            Ajouter
          </Button>
        )}
      </div>

      <FormError>{error}</FormError>

      <div className="overflow-x-auto rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Manager</TableHead>
              <TableHead scope="col">Email</TableHead>
              <TableHead scope="col">Fonction</TableHead>
              <TableHead scope="col">Statut</TableHead>
              <TableHead scope="col" className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {managers.length === 0 ? (
              <EmptyRow
                colSpan={5}
                icon={Users}
                title="Aucun manager rattaché"
                hint={
                  canManage
                    ? "Ajoutez un manager pour lui rattacher des dépenses et une sous-enveloppe."
                    : "Le siège n'a rattaché aucun manager à ce pays."
                }
              />
            ) : (
              managers.map((manager) => (
                <TableRow key={manager.id}>
                  <TableCell>
                    <span className="font-medium">{manager.name}</span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {manager.email || <span className="text-muted-foreground/60">—</span>}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {manager.title || <span className="text-muted-foreground/60">—</span>}
                  </TableCell>
                  <TableCell>
                    {manager.is_active ? (
                      <Badge className={STATUS_TONES.SUCCES}>Actif</Badge>
                    ) : (
                      <Badge variant="secondary">Inactif</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {canManage ? (
                      <>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setEditing(manager)}
                          aria-label={`Modifier ${manager.name}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => void handleDetach(manager)}
                          aria-label={`Retirer ${manager.name} du pays`}
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
                      <span className="text-muted-foreground">—</span>
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
      setError(err instanceof Error ? err.message : "Enregistrement impossible")
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
            {manager ? "Modifier" : "Ajouter"} un manager
          </DialogTitle>
          <DialogDescription>
            {manager
              ? "Mettez à jour les informations du manager."
              : "Créer le manager et le rattacher à ce pays."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid gap-2">
            <Label htmlFor="m-name">Nom</Label>
            <Input
              id="m-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jean Dupont"
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="m-email">Email</Label>
            <Input
              id="m-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jean.dupont@exemple.fr"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="m-title">Fonction</Label>
            <Input
              id="m-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Responsable commercial"
            />
          </div>
          <div className="flex items-center justify-between rounded-lg border p-3">
            <Label htmlFor="m-active" className="text-sm">Actif</Label>
            <Switch id="m-active" checked={active} onCheckedChange={setActive} />
          </div>
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={onClose}>
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
