import { useState, type FormEvent } from "react"
import { Navigate, useNavigate } from "react-router-dom"
import {
  Download,
  Eye,
  EyeOff,
  FileCheck2,
  Loader2,
  Lock,
  MonitorDown,
  ShieldCheck,
  Wallet,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { BrandMark } from "@/components/layout/brand-mark"
import { LanguageToggle } from "@/components/layout/language-toggle"
import { ThemeToggle } from "@/components/layout/theme-toggle"
import { useAuth } from "@/context/use-auth"
import { ApiError, hasFlag } from "@/lib/api"
import { BRAND, copyright } from "@/lib/brand"
import { useInstallPrompt } from "@/lib/install-prompt"

/** Ce que la plateforme garantit, rappelé au moment de la connexion. */
const PROMESSES = [
  { icon: Wallet, titre: "enveloppe_titre", texte: "enveloppe_texte" },
  { icon: FileCheck2, titre: "justifiee_titre", texte: "justifiee_texte" },
  { icon: ShieldCheck, titre: "trace_titre", texte: "trace_texte" },
] as const

export function LoginPage() {
  const { t } = useTranslation()
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const { available: installable, install } = useInstallPrompt()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [code, setCode] = useState("")
  // Le champ du code est toujours là, facultatif : un compte enrôlé se
  // connecte en une seule fois, un compte sans double authentification le
  // laisse vide. Il ne devient exigé que lorsque le serveur le réclame.
  const [totpRequired, setTotpRequired] = useState(false)
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Une session ouverte n'a rien à faire sur l'écran de connexion.
  if (isAuthenticated && !loading) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    // Le bouton reste actionnable : un bouton grisé n'explique pas ce qui
    // manque, là où un message le dit.
    if (!username.trim() || !password) {
      setError(t("auth.identifiants_requis"))
      return
    }
    if (totpRequired && !code.trim()) {
      setError(t("auth.totp.code_requis"))
      return
    }
    setLoading(true)
    setError(null)
    try {
      await login(username, password, code.trim() || undefined)
      navigate("/", { replace: true })
    } catch (err) {
      if (hasFlag(err, "totp_required")) {
        // Identifiants acceptés, code manquant ou faux : on garde la saisie
        // et on demande seulement le code. Le message du serveur ne s'affiche
        // que si un code a bien été présenté.
        setTotpRequired(true)
        setError(
          code.trim() && err instanceof ApiError
            ? (err.fields.code?.join(" ") ?? err.message)
            : null,
        )
        return
      }
      setError(err instanceof Error ? err.message : t("auth.identifiants_invalides"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div className="absolute right-6 top-6 z-10 flex items-center gap-1">
        <LanguageToggle />
        <ThemeToggle />
      </div>
      {/* Panneau de présentation — masqué sur petit écran, où seul le
          formulaire compte. */}
      <aside className="relative hidden flex-col overflow-hidden bg-primary p-12 text-primary-foreground lg:flex">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-primary-foreground/5"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-40 -left-24 h-96 w-96 rounded-full bg-primary-foreground/5"
        />

        <div className="relative flex items-center gap-3">
          {/* Fond clair : l'emblème est en couleur, il disparaîtrait sur le
              panneau sombre. */}
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-foreground p-1.5">
            <BrandMark className="h-full w-full" />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold tracking-tight">{BRAND.name}</p>
            <p className="text-xs text-primary-foreground/60">{t("app.tagline")}</p>
          </div>
        </div>

        <div className="relative flex flex-1 flex-col justify-center py-12">
          <div className="max-w-md">
            <h1 className="text-3xl font-semibold leading-tight tracking-tight">
              {t("auth.slogan_ligne1")}
              <br />
              {t("auth.slogan_ligne2")}
            </h1>
            <p className="mt-4 text-sm leading-relaxed text-primary-foreground/70">
              {t("auth.intro")}
            </p>

            <ul className="mt-10 space-y-6">
              {PROMESSES.map(({ icon: Icon, titre, texte }) => (
                <li key={titre} className="flex gap-4">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-foreground/10">
                    <Icon className="h-4 w-4" aria-hidden />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{t(`auth.promesses.${titre}`)}</p>
                    <p className="mt-0.5 text-sm text-primary-foreground/60">
                      {t(`auth.promesses.${texte}`)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="relative space-y-1 text-xs text-primary-foreground/50">
          <p>{t("auth.acces_reserve")}</p>
          <p>
            {copyright()} {t("layout.version")} {BRAND.version} — {BRAND.developer}.
          </p>
        </div>
      </aside>

      {/* Formulaire */}
      <main className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          {/* Reprend l'identité sur mobile, où le panneau est masqué. */}
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <BrandMark className="h-11 w-11" />
            <div className="leading-tight">
              <p className="font-semibold tracking-tight">{BRAND.name}</p>
              <p className="text-xs text-muted-foreground">{t("app.tagline")}</p>
            </div>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-semibold tracking-tight">{t("auth.connexion")}</h2>
            <p className="mt-1.5 text-sm text-muted-foreground">{t("auth.sous_titre")}</p>
          </div>

          <form onSubmit={handleSubmit} className="grid gap-5" noValidate>
            {/* `role="alert"` : l'échec doit être annoncé aux lecteurs d'écran,
                pas seulement apparaître à l'écran. */}
            {error && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
              >
                <Lock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                {error}
              </p>
            )}

            <div className="grid gap-2">
              <Label htmlFor="username">{t("auth.identifiant")}</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="prenom.innov"
                autoComplete="username"
                required
                className="h-10"
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="password">{t("auth.mot_de_passe")}</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={visible ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  className="h-10 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setVisible((shown) => !shown)}
                  aria-label={visible ? t("auth.masquer_mdp") : t("auth.afficher_mdp")}
                  aria-pressed={visible}
                  className="absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {visible ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            <div className="grid gap-2">
                <Label htmlFor="totp-code">{t("auth.totp.code")}</Label>
                <Input
                  id="totp-code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required={totpRequired}
                  className="h-10 font-mono tracking-widest"
                />
                <p className="text-xs text-muted-foreground">
                  {totpRequired ? t("auth.totp.aide") : t("auth.totp.aide_connexion")}
                </p>
                {/* Rien d'automatique : seul un administrateur peut
                    réinitialiser l'enrôlement, et le lien le dit. */}
                <details className="text-xs text-muted-foreground">
                  <summary className="cursor-pointer underline underline-offset-4 hover:text-foreground">
                    {t("auth.totp.plus_acces")}
                  </summary>
                  <p className="mt-1">{t("auth.totp.plus_acces_texte")}</p>
                </details>
              </div>

            <Button
              type="submit"
              disabled={loading}
              className="mt-1 h-10 w-full"
            >
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("auth.se_connecter")}
            </Button>
          </form>

          <p className="mt-8 text-center text-xs text-muted-foreground">{t("auth.oubli")}</p>

          {/* Application de bureau : la note reste discrète, et le bouton
              n'apparaît que si le navigateur sait installer la page. */}
          <div className="mt-6 flex items-start gap-2 rounded-lg border border-border/60 bg-card/60 p-3 text-xs text-muted-foreground">
            <MonitorDown className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="space-y-2">
              <p>{t("pwa.note_connexion")}</p>
              {installable && (
                <Button variant="outline" size="xs" onClick={() => void install()}>
                  <Download className="mr-1 h-3.5 w-3.5" aria-hidden />
                  {t("pwa.installer")}
                </Button>
              )}
            </div>
          </div>

          {/* Le panneau porte déjà ces mentions sur grand écran. */}
          <p className="mt-6 text-center text-xs text-muted-foreground/70 lg:hidden">
            {copyright()}
            <br />
            {t("layout.version")} {BRAND.version} — {BRAND.developer}
          </p>
        </div>
      </main>
    </div>
  )
}
