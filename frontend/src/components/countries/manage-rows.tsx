import { useState, type FormEvent, type ReactNode } from "react"
import { Inbox, Loader2, Pencil, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
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

export interface FormField {
  key: string
  label: string
  placeholder?: string
  type?: string
  /** Rend une liste déroulante plutôt qu'un champ libre. */
  options?: { value: string; label: string }[]
  /** Un champ facultatif ne bloque pas l'enregistrement s'il reste vide. */
  optional?: boolean
  /** Saisie décimale : clavier numérique, virgule acceptée. */
  decimal?: boolean
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
  formFields: FormField[]
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
  const [editing, setEditing] = useState<T | "nouveau" | null>(null)

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
          <Button size="sm" onClick={() => setEditing("nouveau")}>
            <Plus className="mr-1 h-4 w-4" aria-hidden />
            {createLabel}
          </Button>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-border/60 shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => (
                <TableHead scope="col" key={String(col.key)}>{col.header}</TableHead>
              ))}
              {canManage && <TableHead scope="col" className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <SkeletonRows columns={columns.length + (canManage ? 1 : 0)} rows={3} />
            ) : rows.length === 0 ? (
              <EmptyRow
                colSpan={columns.length + (canManage ? 1 : 0)}
                icon={Inbox}
                title={emptyMessage}
                hint={canManage ? `Cliquez sur « ${createLabel} » pour créer la première entrée.` : undefined}
              />
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
                        onClick={() => setEditing(item)}
                        aria-label={`Modifier ${String((item as Record<string, unknown>).name ?? (item as Record<string, unknown>).label ?? (item as Record<string, unknown>).code ?? item.id)}`}
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

      {editing !== null && (
        <RowDialog
          key={editing === "nouveau" ? "nouveau" : editing.id}
          title={title}
          item={editing === "nouveau" ? null : editing}
          defaultForm={defaultForm}
          formFields={formFields}
          extraForm={extraForm}
          detectActive={detectActive}
          onSave={onSave}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

function RowDialog<T extends { id: number }>({
  title,
  item,
  defaultForm,
  formFields,
  extraForm,
  detectActive,
  onSave,
  onClose,
}: {
  title: string
  item: T | null
  defaultForm: Record<string, string>
  formFields: FormField[]
  extraForm?: ReactNode
  detectActive?: (item: T) => boolean
  onSave: (data: Record<string, unknown>, id?: number) => Promise<void>
  onClose: () => void
}) {
  const [form, setForm] = useState<Record<string, string>>(() =>
    item
      ? Object.fromEntries(
          formFields.map((f) => [
            f.key,
            String((item as unknown as Record<string, unknown>)[f.key] ?? ""),
          ]),
        )
      : defaultForm,
  )
  const [active, setActive] = useState(item && detectActive ? detectActive(item) : true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const manquant = formFields.find((f) => !f.optional && !form[f.key]?.trim())
    if (manquant) {
      setError(`Le champ « ${manquant.label} » est obligatoire.`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave({ ...form, is_active: active }, item?.id)
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
          <DialogTitle>
            {item ? "Modifier" : "Ajouter"} — {title}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          {formFields.map((f) => (
            <div className="grid gap-2" key={f.key}>
              <Label htmlFor={`row-${f.key}`}>
                {f.label}
                {f.optional && <span className="ml-1 text-xs text-muted-foreground">(facultatif)</span>}
              </Label>
              {f.options ? (
                <NativeSelect
                  id={`row-${f.key}`}
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
                  id={`row-${f.key}`}
                  type={f.type ?? "text"}
                  inputMode={f.decimal ? "decimal" : undefined}
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
            <Label htmlFor="row-active" className="text-sm">Actif</Label>
            <Switch id="row-active" checked={active} onCheckedChange={setActive} />
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
