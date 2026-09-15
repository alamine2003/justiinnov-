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
import { BrandLogo } from "@/components/layout/brand-logo"
import { LanguageToggle } from "@/components/layout/language-toggle"
import { ThemeToggle } from "@/components/layout/theme-toggle"
import { useAuth } from "@/context/use-auth"
import { ApiError, hasFlag } from "@/lib/api"
import { BRAND, copyright } from "@/lib/brand"
import { useInstallPrompt } from "@/lib/install-prompt"
import { CIRCUIT } from "@/lib/labels"
import { currentLocale } from "@/i18n"
import { FILIALES } from "@/lib/perimetre"
import { WORKFLOW_STYLE } from "@/lib/status-styles"
import type { WorkflowStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

/**
 * Ce que la plateforme garantit, rappelé au moment de la connexion. Les
 * trois pastilles partagent la teinte du bandeau : une couleur de marque
 * dit une action, une alerte ou un manque (DESIGN.md), elle ne décore pas
 * — le corail sur « rien ne se perd » disait le contraire du texte.
 */
const PROMESSES = [
  { icon: Wallet, titre: "enveloppe_titre", texte: "enveloppe_texte" },
  { icon: FileCheck2, titre: "justifiee_titre", texte: "justifiee_texte" },
  { icon: ShieldCheck, titre: "trace_titre", texte: "trace_texte" },
] as const

/** Le fond du badge d'un statut, tiré de `WORKFLOW_STYLE` : la page d'accueil ne recopie aucune teinte. */
const fondDe = (statut: WorkflowStatus) =>
  WORKFLOW_STYLE[statut].split(" ").find((classe) => classe.startsWith("bg-")) ?? ""

/**
 * Sous quel libellé chaque statut se raconte sur l'accueil. `satisfies`
 * exige une entrée par statut : un sixième état ajouté au circuit ne
 * passera pas la compilation sans qu'on ait décidé ce qu'il dit ici.
 */
const LIBELLE_DE = {
  draft: "brouillon",
  submitted: "soumis",
  in_review: "controle",
  justified: "justifie",
  unjustified: "justifie",
  closed: "cloture",
} as const satisfies Record<WorkflowStatus, string>

/**
 * Les états du circuit, dans l'ordre — celui de `CIRCUIT` (`lib/labels.ts`),
 * jamais une liste recopiée ici —, chacun sous la couleur qu'il porte dans
 * l'application (`WORKFLOW_STYLE`).
 */
const ETAPES = CIRCUIT.map((statut) => ({
  statut,
  cle: LIBELLE_DE[statut],
  barre: fondDe(statut),
}))

/** Les trois couleurs de la marque, en bandeau — le trait du logo. */
function BandeauDeMarque({ className }: { className?: string }) {
  return (
    <div aria-hidden className={cn("flex overflow-hidden", className)}>
      <span className="h-full flex-1 bg-destructive" />
      <span className="h-full flex-1 bg-statut-attente" />
      <span className="h-full flex-1 bg-marque" />
    </div>
  )
}

export function LoginPage() {
  const { t } = useTranslation()
  const { isAuthenticated } = useAuth()

  // Une session ouverte n'a rien à faire sur l'écran de connexion.
  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return (
    // Toute la page est le contenu principal : le saut au contenu doit
    // atteindre le circuit et le périmètre, pas seulement la carte.
    <main className="min-h-screen bg-background">
      {/* Bandeau : la promesse à gauche, la connexion à droite. */}
      <section className="relative overflow-hidden bg-banniere text-banniere-foreground">
        <BandeauDeMarque className="h-1.5 w-full" />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-40 -top-40 h-[28rem] w-[28rem] rounded-full bg-banniere-foreground/5"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-48 -left-32 h-[28rem] w-[28rem] rounded-full bg-banniere-foreground/5"
        />

        <div className="relative mx-auto w-full max-w-7xl px-6">
          <header className="flex h-20 items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              {/* Le logo suit la couleur du texte du bandeau : clair sur marine. */}
              <BrandLogo className="h-8 w-auto" />
              <span
                aria-hidden
                className="hidden h-5 border-l border-banniere-bordure sm:block"
              />
              <p className="hidden truncate text-sm text-banniere-muted sm:block">
                {t("app.tagline")}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <LanguageToggle segmented />
              <ThemeToggle />
            </div>
          </header>

          <div className="grid gap-12 py-10 lg:grid-cols-[1.15fr_minmax(0,26rem)] lg:items-center lg:gap-16 lg:py-16">
            <div className="max-w-2xl">
              <BandeauDeMarque className="h-2 w-36 gap-1.5 rounded-full *:rounded-full" />
              <h1 className="mt-8 text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
                {t("auth.slogan_ligne1")}
                <br />
                {t("auth.slogan_ligne2")}
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-banniere-muted">
                {t("auth.intro")}
              </p>

              <ul className="mt-12 grid gap-8 sm:grid-cols-3">
                {PROMESSES.map(({ icon: Icon, titre, texte }) => (
                  <li key={titre}>
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-banniere-bordure text-banniere-accent">
                      <Icon className="h-5 w-5" aria-hidden />
                    </div>
                    <p className="mt-4 text-sm font-semibold">{t(`auth.promesses.${titre}`)}</p>
                    <p className="mt-1.5 text-sm leading-relaxed text-banniere-muted">
                      {t(`auth.promesses.${texte}`)}
                    </p>
                  </li>
                ))}
              </ul>
            </div>

            <LoginCard />
          </div>
        </div>
      </section>

      {/* Le circuit, tel que l'application l'applique. */}
      <section className="border-b border-border/60 bg-card">
        <div className="mx-auto w-full max-w-7xl px-6 py-16">
          <div className="grid gap-6 lg:grid-cols-[1fr_minmax(0,32rem)] lg:items-start lg:gap-16">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-marque-fort">
                {t("accueil.circuit.sur_titre")}
              </p>
              <h2 className="mt-3 max-w-xl text-3xl font-semibold leading-tight tracking-tight">
                {t("accueil.circuit.titre")}
              </h2>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground lg:pt-8">
              {t("accueil.circuit.texte")}
            </p>
          </div>

          <ol className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-5 lg:gap-0 lg:divide-x lg:divide-border/60">
            {ETAPES.map(({ statut, cle, barre }, index) => (
              <li key={statut} className="lg:px-6 lg:first:pl-0 lg:last:pr-0">
                <div aria-hidden className={cn("h-1 w-full rounded-full", barre)} />
                <p className="mt-5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {String(index + 1).padStart(2, "0")} · {t(`accueil.circuit.etapes.${cle}.acteur`)}
                </p>
                <h3 className="mt-2 text-lg font-semibold">
                  {t(`accueil.circuit.etapes.${cle}.titre`)}
                  {statut === "justified" && (
                    <span className="font-normal text-muted-foreground">
                      {" "}
                      {t("accueil.circuit.etapes.justifie.ou_non")}
                    </span>
                  )}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {t(`accueil.circuit.etapes.${cle}.texte`)}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Le périmètre : les filiales, et rien d'autre. */}
      <section className="bg-background">
        <div className="mx-auto w-full max-w-7xl px-6 py-16">
          <div className="grid gap-8 lg:grid-cols-[minmax(0,26rem)_1fr] lg:gap-16">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-marque-fort">
                {t("accueil.perimetre.sur_titre")}
              </p>
              <h2 className="mt-3 text-3xl font-semibold leading-tight tracking-tight">
                {t("accueil.perimetre.titre")}
              </h2>
              <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
                {t("accueil.perimetre.texte")}
              </p>
            </div>
            <div>
              <Filiales />
              <p className="mt-5 text-xs text-muted-foreground">
                {t("accueil.perimetre.legende")}
              </p>
            </div>
          </div>
        </div>
      </section>

      <footer className="bg-banniere text-banniere-muted">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-6 py-6 text-xs sm:flex-row sm:items-center sm:justify-between">
          <p className="flex items-center gap-3">
            <BrandLogo className="h-5 w-auto text-banniere-foreground" />
            <span>{t("auth.acces_reserve")}</span>
          </p>
          <p>
            {copyright()} · {t("layout.version")} {BRAND.version} — {BRAND.developer}
          </p>
        </div>
      </footer>
    </main>
  )
}

/** Les dix-sept filiales, dans l'ordre alphabétique de la langue affichée. */
function Filiales() {
  const { t } = useTranslation()
  const locale = currentLocale()
  const noms = FILIALES.map((code) => ({ code, nom: t(`filiales.${code}`) })).sort((a, b) =>
    a.nom.localeCompare(b.nom, locale),
  )
  return (
    <ul className="flex flex-wrap gap-2" aria-label={t("accueil.perimetre.sur_titre")}>
      {noms.map(({ code, nom }) => (
        <li
          key={code}
          className="rounded-lg border border-border/60 bg-card px-3 py-1.5 text-sm text-card-foreground"
        >
          {nom}
        </li>
      ))}
    </ul>
  )
}

/**
 * Le formulaire de connexion, sur sa carte.
 *
 * Le champ du code est toujours là, facultatif : un compte enrôlé se
 * connecte en une seule fois, un compte sans double authentification le
 * laisse vide. Il ne devient exigé que lorsque le serveur le réclame.
 */
function LoginCard() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const navigate = useNavigate()
  const { available: installable, install } = useInstallPrompt()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [code, setCode] = useState("")
  const [totpRequired, setTotpRequired] = useState(false)
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

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
    <div className="rounded-2xl bg-card p-8 text-card-foreground shadow-2xl ring-1 ring-foreground/10">
      <div className="mb-7">
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
              {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
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
          {/* Rien d'automatique : seul un administrateur peut réinitialiser
              l'enrôlement, et le lien le dit. */}
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer underline underline-offset-4 hover:text-foreground">
              {t("auth.totp.plus_acces")}
            </summary>
            <p className="mt-1">{t("auth.totp.plus_acces_texte")}</p>
          </details>
        </div>

        <Button type="submit" disabled={loading} className="mt-1 h-11 w-full text-base">
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t("auth.se_connecter")}
        </Button>
      </form>

      <p className="mt-6 text-center text-xs text-muted-foreground">{t("auth.oubli")}</p>

      {/* Application de bureau : la note reste discrète, et le bouton
          n'apparaît que si le navigateur sait installer la page. */}
      <div className="mt-5 flex items-start gap-2 rounded-lg border border-border/60 bg-muted/40 p-3 text-xs text-muted-foreground">
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
    </div>
  )
}
