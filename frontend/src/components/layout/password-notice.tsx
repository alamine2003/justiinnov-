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
 * Impose le remplacement du mot de passe distribué par le siège.
 *
 * Le mot de passe de création a circulé — par message, par téléphone, sur un
 * papier. Tant qu'il n'a pas été remplacé, le compte n'est pas réellement
 * personnel : ce qu'il signe ne prouve rien.
 *
 * Le blocage réel est côté serveur ; cet écran évite d'envoyer l'utilisateur
 * se heurter à des refus qu'il ne comprendrait pas. Il ne se ferme pas :
 * proposer « Plus tard » serait proposer une porte qui ne mène nulle part.
 */
export function PasswordNotice() {
  const { me, refreshProfile } = useAuth()
  const [open, setOpen] = useState(true)
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
        <AlertTitle>Mot de passe à remplacer</AlertTitle>
        <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
          <span>
            Votre mot de passe a été défini par le siège : il a circulé, et
            tant qu'il n'est pas remplacé vos actions ne vous engagent pas.
            La plateforme reste fermée jusque-là.
          </span>
          <Button size="sm" onClick={() => setOpen(true)}>
            Changer maintenant
          </Button>
        </AlertDescription>
      </Alert>

      {/* Ni « Plus tard », ni fermeture au clic extérieur : le serveur refuse
          tout le reste, une sortie ne mènerait nulle part. `onOpenChange`
          ignoré volontairement — la boîte ne se referme que par la réussite
          du changement, qui fait disparaître le composant. */}
      <Dialog open={open} onOpenChange={() => {}} disablePointerDismissal>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Choisissez votre mot de passe</DialogTitle>
            <DialogDescription>
              Au moins 10 caractères, ni trop courant ni uniquement numérique.
              Il ne doit être connu que de vous.
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
                <Button type="submit" disabled={saving}>
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
