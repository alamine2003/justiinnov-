import { useState, type FormEvent } from "react"
import { KeyRound, Loader2 } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { useAuth } from "@/context/auth"
import { changePassword } from "@/lib/accounts"

/**
 * Invite à remplacer le mot de passe distribué par le siège.
 *
 * Volontairement non bloquant pendant la phase de test : le compte reste
 * utilisable, mais l'invitation persiste tant que le mot de passe provisoire
 * n'a pas été changé.
 */
export function PasswordNotice() {
  const { me, refreshProfile } = useAuth()
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [confirmation, setConfirmation] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  if (!me?.must_change_password) {
    return null
  }

  const reset = () => {
    setCurrent("")
    setNext("")
    setConfirmation("")
    setError(null)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (next !== confirmation) {
      setError("Les deux saisies ne correspondent pas.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await changePassword(current, next)
      await refreshProfile()
      setOpen(false)
      reset()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Changement impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Alert className="mb-6 border-amber-500/40 bg-amber-500/10">
        <KeyRound className="h-4 w-4" />
        <AlertTitle>Mot de passe provisoire</AlertTitle>
        <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
          <span>
            Votre mot de passe a été défini par le siège. Remplacez-le par un
            mot de passe personnel.
          </span>
          <Button size="sm" onClick={() => setOpen(true)}>
            Changer maintenant
          </Button>
        </AlertDescription>
      </Alert>

      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o)
          if (!o) reset()
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Changer le mot de passe</DialogTitle>
            <DialogDescription>
              Au moins 10 caractères, ni trop courant ni uniquement numérique.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="grid gap-4 py-2">
            {error && (
              <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </p>
            )}
            <div className="grid gap-2">
              <Label htmlFor="pwd-current">Mot de passe actuel</Label>
              <Input
                id="pwd-current"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pwd-new">Nouveau mot de passe</Label>
              <Input
                id="pwd-new"
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pwd-confirm">Confirmation</Label>
              <Input
                id="pwd-confirm"
                type="password"
                autoComplete="new-password"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                required
              />
            </div>
            <DialogFooter>
              <div>
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                  Plus tard
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
    </>
  )
}
