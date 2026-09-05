import { useEffect, useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import i18next from "i18next"
import { Check, Copy, Loader2, ShieldCheck } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/use-auth"
import { confirmTwoFactor, enrolTwoFactor, totpEnrolmentRequired } from "@/lib/accounts"
import { ApiError } from "@/lib/api"
import type { TotpEnrolment } from "@/lib/types"

/**
 * Enrôlement de la double authentification.
 *
 * Un mot de passe seul, réutilisé ou intercepté, suffirait à signer une
 * justification au nom d'un autre. Deux cas mènent ici : le serveur impose
 * la double authentification (`totp_required`) et la plateforme reste
 * fermée tant que l'application d'authentification n'est pas liée, comme
 * pour un mot de passe provisoire ; ou le titulaire vient l'activer de
 * lui-même depuis le menu du compte, et peut remettre à plus tard.
 *
 * Le secret est généré par le serveur et montré une seule fois : en QR pour
 * qui peut scanner, en clair pour qui doit le saisir. Le premier code valide
 * confirme l'enrôlement et renvoie vers l'application.
 */
export function TotpNotice() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { me, refreshProfile } = useAuth()
  const [enrolment, setEnrolment] = useState<TotpEnrolment | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [code, setCode] = useState("")
  const [codeError, setCodeError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [copied, setCopied] = useState(false)

  const aEnroler = me?.totp_confirmed === false
  const imposee = totpEnrolmentRequired(me)

  // Un seul enrôlement par écran : chaque appel régénère le secret, et un
  // QR remplacé sous les yeux de la personne — à un changement de langue,
  // par exemple — n'aurait plus rien à voir avec ce que son application a
  // scanné. `t` reste donc hors des dépendances.
  useEffect(() => {
    if (!aEnroler) return
    let active = true
    enrolTwoFactor()
      .then((data) => {
        if (active) setEnrolment(data)
      })
      .catch((e: unknown) => {
        if (active) {
          setLoadError(
            e instanceof Error ? e.message : i18next.t("auth.totp.enrolement_impossible"),
          )
        }
      })
    return () => {
      active = false
    }
  }, [aEnroler])

  if (!aEnroler) {
    return null
  }

  const copier = async () => {
    if (!enrolment) return
    try {
      await navigator.clipboard.writeText(enrolment.secret)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      // Presse-papiers indisponible : le secret reste lisible à l'écran.
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const saisi = code.replace(/\s+/g, "")
    if (!/^\d{6}$/.test(saisi)) {
      setCodeError(t("auth.totp.code_six_chiffres"))
      return
    }
    setSaving(true)
    setError(null)
    setCodeError(null)
    try {
      await confirmTwoFactor(saisi)
      // Le profil relu porte `totp_confirmed: true` : la garde de routes
      // rend alors l'application.
      await refreshProfile()
    } catch (err) {
      // Un code refusé s'affiche sans vider le champ.
      if (err instanceof ApiError && err.fields.code) {
        setCodeError(err.fields.code.join(" "))
      } else {
        setError(err instanceof Error ? err.message : t("auth.totp.confirmation_impossible"))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      {imposee ? (
        <Alert className="border-statut-attente/40 bg-statut-attente/10">
          <ShieldCheck className="h-4 w-4" />
          <AlertTitle>{t("auth.totp.a_enroler_titre")}</AlertTitle>
          <AlertDescription>{t("auth.totp.a_enroler_texte")}</AlertDescription>
        </Alert>
      ) : (
        <Alert>
          <ShieldCheck className="h-4 w-4" />
          <AlertTitle>{t("auth.totp.volontaire_titre")}</AlertTitle>
          <AlertDescription>{t("auth.totp.volontaire_texte")}</AlertDescription>
        </Alert>
      )}

      <Card className="border-border/60 shadow-sm">
        <CardHeader>
          <CardTitle className="text-sm font-semibold">{t("auth.totp.enroler")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("auth.totp.consigne")}</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
            <FormError>{loadError ?? error}</FormError>

            {enrolment ? (
              <>
                <div className="flex justify-center">
                  {/* Le PNG vient du serveur ; l'URI reste disponible pour
                      les applications qui la lisent directement. */}
                  <img
                    src={`data:image/png;base64,${enrolment.qr_png_base64}`}
                    alt={t("auth.totp.qr_alt")}
                    className="h-48 w-48 rounded-lg border border-border/60 bg-card p-2"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="totp-secret">{t("auth.totp.secret")}</Label>
                  <div className="flex items-center gap-2">
                    <output
                      id="totp-secret"
                      className="flex-1 select-all break-all rounded-lg border border-border/60 bg-muted px-3 py-2 font-mono text-sm"
                    >
                      {enrolment.secret}
                    </output>
                    <Button type="button" variant="outline" size="sm" onClick={() => void copier()}>
                      {copied ? (
                        <Check className="mr-1 h-4 w-4" aria-hidden />
                      ) : (
                        <Copy className="mr-1 h-4 w-4" aria-hidden />
                      )}
                      {copied ? t("auth.totp.copie") : t("auth.totp.copier")}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">{t("auth.totp.secret_aide")}</p>
                </div>
              </>
            ) : (
              !loadError && (
                <div className="flex h-48 items-center justify-center" aria-busy="true">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  <span className="sr-only">{t("commun.chargement")}</span>
                </div>
              )
            )}

            <div className="grid gap-2">
              <Label htmlFor="totp-confirm-code">{t("auth.totp.code_six")}</Label>
              <Input
                id="totp-confirm-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]*"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                aria-invalid={Boolean(codeError)}
                aria-describedby={codeError ? "totp-confirm-code-error" : undefined}
                required
                className="font-mono tracking-widest"
              />
              {codeError && (
                <p id="totp-confirm-code-error" role="alert" className="text-xs text-destructive">
                  {codeError}
                </p>
              )}
            </div>

            <div className="flex justify-end gap-2">
              {/* Facultative : on peut repartir sans avoir rien lié. */}
              {!imposee && (
                <Button type="button" variant="outline" onClick={() => navigate("/")}>
                  {t("auth.totp.plus_tard")}
                </Button>
              )}
              <Button type="submit" disabled={saving}>
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("commun.confirmer")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
