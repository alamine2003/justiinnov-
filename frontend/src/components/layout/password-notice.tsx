import { useState, type FormEvent } from "react"
import { KeyRound, Loader2 } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/use-auth"
import { changePassword } from "@/lib/accounts"

/**
 * Impose le remplacement du mot de passe distribué par le siège.
 *
 * Le mot de passe de création a circulé — par message, par téléphone, sur un
 * papier. Tant qu'il n'a pas été remplacé, le compte n'est pas réellement
 * personnel : ce qu'il signe ne prouve rien.
 *
 * Le blocage réel est côté serveur ; cet écran évite d'envoyer l'utilisateur
 * se heurter à des refus qu'il ne comprendrait pas. Il n'a ni « Plus tard »
 * ni fermeture : la seule sortie est la réussite du changement, qui renvoie
 * vers l'application.
 */
export function PasswordNotice() {
  const { me, refreshProfile, replaceToken } = useAuth()
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [confirmation, setConfirmation] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  if (!me?.must_change_password) {
    return null
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
      // Le serveur révoque l'ancien jeton avec l'ancien mot de passe : sans
      // le nouveau, la requête suivante serait un 401.
      const { token } = await changePassword(current, next)
      if (token) replaceToken(token)
      await refreshProfile()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Changement impossible")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <Alert className="border-statut-attente/40 bg-statut-attente/10">
        <KeyRound className="h-4 w-4" />
        <AlertTitle>Mot de passe à remplacer</AlertTitle>
        <AlertDescription>
          Votre mot de passe a été défini par le siège : il a circulé, et tant
          qu'il n'est pas remplacé vos actions ne vous engagent pas. La
          plateforme reste fermée jusque-là.
        </AlertDescription>
      </Alert>

      <Card className="border-border/60 shadow-sm">
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Choisissez votre mot de passe</CardTitle>
          <p className="text-xs text-muted-foreground">
            Au moins 10 caractères, ni trop courant ni uniquement numérique. Il
            ne doit être connu que de vous.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-4">
            <FormError>{error}</FormError>
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
            <div className="flex justify-end">
              <Button type="submit" disabled={saving}>
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Enregistrer
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
