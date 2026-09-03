import { useState, type FormEvent, type ReactNode } from "react"
import { Loader2, Pencil, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
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

export interface ColumnDef<T> {
  key: keyof T | string
  header: string
  render?: (item: T) => ReactNode
}

interface ManageRowsProps<T extends { id: number }> {
  title: string
  description?: string
  rows: T[]
  columns: ColumnDef<T>[]
  loading?: boolean
  emptyMessage?: string
  createLabel?: string
  onSave: (data: Record<string, unknown>, id?: number) => Promise<void>
  /** Masque les actions que le rôle ne peut pas exécuter. */
  canManage?: boolean
  detectActive?: (item: T) => boolean
  defaultForm: Record<string, string>
  formFields: {
    key: string
    label: string
    placeholder?: string
    type?: string
    /** Rend une liste déroulante plutôt qu'un champ libre. */
    options?: { value: string; label: string }[]
    /** Un champ facultatif ne bloque pas l'enregistrement s'il reste vide. */
    optional?: boolean
  }[]
  extraForm?: ReactNode
}

export function ManageRows<T extends { id: number }>({
  title,
  description,
  rows,
  columns,
  loading,
  emptyMessage = "Aucune entrée.",
  createLabel = "Ajouter",
  onSave,
  canManage = true,
  detectActive,
  defaultForm,
  formFields,
  extraForm,
}: ManageRowsProps<T>) {
  const [open, setOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<Record<string, string>>(defaultForm)
  const [active, setActive] = useState(true)
  const [saving, setSaving] = useState(false)

  const openCreate = () => {
    setEditingId(null)
    setForm(defaultForm)
    setActive(true)
    setOpen(true)
  }

  const openEdit = (item: T) => {
    setEditingId(item.id)
    setForm(
      Object.fromEntries(
        formFields.map((f) => [
          f.key,
          String((item as unknown as Record<string, unknown>)[f.key] ?? ""),
        ]),
      ),
    )
    setActive(detectActive ? detectActive(item) : true)
    setOpen(true)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await onSave({ ...form, is_active: active }, editingId ?? undefined)
      setOpen(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>
        {canManage && (
          <Button size="sm" onClick={openCreate}>
            <Plus className="mr-1 h-4 w-4" />
            {createLabel}
          </Button>
        )}
      </div>

      <div className="overflow-hidden rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => (
                <TableHead key={String(col.key)}>{col.header}</TableHead>
              ))}
              {canManage && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={columns.length + (canManage ? 1 : 0)} className="h-16">
                  <div className="h-4 animate-pulse rounded bg-muted" />
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length + (canManage ? 1 : 0)} className="h-16 text-center text-muted-foreground">
                  {emptyMessage}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((item) => (
                <TableRow key={item.id}>
                  {columns.map((col) => (
                    <TableCell key={String(col.key)}>
                      {col.render
                        ? col.render(item)
                        : (item[col.key as keyof T] as ReactNode)}
                    </TableCell>
                  ))}
                  {canManage && (
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openEdit(item)}
                        aria-label="Modifier"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  )}
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
          } else {
            setOpen(true)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingId !== null ? "Modifier" : "Ajouter"} — {title}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="grid gap-4 py-2">
            {formFields.map((f) => (
              <div className="grid gap-2" key={f.key}>
                <Label htmlFor={f.key}>{f.label}</Label>
                {f.options ? (
                  <NativeSelect
                    id={f.key}
                    value={form[f.key] ?? ""}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, [f.key]: e.target.value }))
                    }
                    required={!f.optional}
                  >
                    {f.options.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </NativeSelect>
                ) : (
                  <Input
                    id={f.key}
                    type={f.type ?? "text"}
                    value={form[f.key] ?? ""}
                    placeholder={f.placeholder}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, [f.key]: e.target.value }))
                    }
                    required={!f.optional}
                  />
                )}
              </div>
            ))}
            {extraForm}
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