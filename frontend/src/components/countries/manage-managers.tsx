import { useState, type FormEvent } from "react"
import { Link2, Loader2, Pencil, Plus, Unlink } from "lucide-react"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
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
import type { Manager } from "@/lib/types"

interface ManageManagersProps {
  countryId: number
  managers: Manager[]
  onRefresh: () => void
  /** Le référentiel des managers relève du siège. */
  canManage: boolean
}

interface ManagerForm {
  name: string
  email: string
  title: string
}

const EMPTY_FORM: ManagerForm = { name: "", email: "", title: "" }

export function ManageManagers({
  countryId,
  managers,
  onRefresh,
  canManage,
}: ManageManagersProps) {
  const [open, setOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<ManagerForm>(EMPTY_FORM)
  const [active, setActive] = useState(true)
  const [saving, setSaving] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)

  const setField = (field: keyof ManagerForm, value: string) => {
    setForm((f) => ({ ...f, [field]: value }))
  }

  const openCreate = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setActive(true)
    setOpen(true)
  }

  const openEdit = (manager: Manager) => {
    setEditingId(manager.id)
    setForm({
      name: manager.name,
      email: manager.email ?? "",
      title: manager.title ?? "",
    })
    setActive(manager.is_active)
    setOpen(true)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form, is_active: active }
      if (editingId !== null) {
        await updateManager(editingId, payload)
      } else {
        const created = await createManager(payload)
        await updateCountryManagers(countryId, [
          ...managers.map((m) => m.id),
          created.id,
        ])
      }
      setOpen(false)
      await onRefresh()
    } finally {
      setSaving(false)
    }
  }

  const handleDetach = async (manager: Manager) => {
    setBusyId(manager.id)
    try {
      await updateCountryManagers(
        countryId,
        managers.filter((m) => m.id !== manager.id).map((m) => m.id),
      )
      await onRefresh()
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
          <Button size="sm" onClick={openCreate}>
            <Plus className="mr-1 h-4 w-4" />
            Ajouter
          </Button>
        )}
      </div>

      <div className="overflow-hidden rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Manager</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Fonction</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {managers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-16 text-center text-muted-foreground">
                  Aucun manager rattaché.
                </TableCell>
              </TableRow>
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
                      <Badge className="bg-emerald-500 shadow-sm shadow-emerald-500/20 hover:bg-emerald-500">
                        Actif
                      </Badge>
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
                          onClick={() => openEdit(manager)}
                          aria-label="Modifier"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDetach(manager)}
                          aria-label="Retirer du pays"
                          title="Retirer ce manager du pays"
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

      <Dialog
        open={open}
        onOpenChange={(o) => {
          if (!o) {
            setOpen(false)
            setEditingId(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Link2 className="h-4 w-4" />
              {editingId !== null ? "Modifier" : "Ajouter"} un manager
            </DialogTitle>
            <DialogDescription>
              {editingId !== null
                ? "Mettez à jour les informations du manager."
                : "Créer le manager et le rattacher à ce pays."}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="grid gap-4 py-2">
            <div className="grid gap-2">
              <Label htmlFor="m-name">Nom</Label>
              <Input
                id="m-name"
                value={form.name}
                onChange={(e) => setField("name", e.target.value)}
                placeholder="Jean Dupont"
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="m-email">Email</Label>
              <Input
                id="m-email"
                type="email"
                value={form.email}
                onChange={(e) => setField("email", e.target.value)}
                placeholder="jean.dupont@exemple.fr"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="m-title">Fonction</Label>
              <Input
                id="m-title"
                value={form.title}
                onChange={(e) => setField("title", e.target.value)}
                placeholder="Responsable commercial"
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-3">
              <p className="text-sm">Actif</p>
              <Switch checked={active} onCheckedChange={setActive} />
            </div>
            <DialogFooter>
              <div>
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>
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
    </div>
  )
}
