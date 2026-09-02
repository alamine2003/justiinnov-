import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import {
  Eye,
  EyeOff,
  FileCheck2,
  Loader2,
  Lock,
  ShieldCheck,
  Wallet,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/auth"

/** Ce que la plateforme garantit, rappelé au moment de la connexion. */
const PROMESSES = [
  {
    icon: Wallet,
    titre: "Une enveloppe par pays",
    texte: "Budget attribué, engagé, consommé et disponible, en temps réel.",
  },
  {
    icon: FileCheck2,
    titre: "Chaque dépense justifiée",
    texte: "Date, lieu, bénéficiaire et pièce à l'appui, pour chaque montant.",
  },
  {
    icon: ShieldCheck,
    titre: "Rien ne se perd",
    texte: "Une dépense déclarée est définitive et toute action est tracée.",
  },
]

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    // Le bouton reste actionnable : un bouton grisé n'explique pas ce qui
    // manque, là où un message le dit.
    if (!username.trim() || !password) {
      setError("Renseignez votre identifiant et votre mot de passe.")
      return
    }
    setLoading(true)
    setError(null)
    try {
      await login(username, password)
      navigate("/", { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Identifiants invalides")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
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
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-foreground/10">
            <Wallet className="h-5 w-5" />
          </div>
          <span className="text-sm font-medium tracking-tight">
            Contrôle budgétaire
          </span>
        </div>

        <div className="relative flex flex-1 flex-col justify-center py-12">
          <div className="max-w-md">
            <h1 className="text-3xl font-semibold leading-tight tracking-tight">
              Savoir où va chaque franc,
              <br />
              et ce qui le justifie.
            </h1>
            <p className="mt-4 text-sm leading-relaxed text-primary-foreground/70">
              Le suivi budgétaire des pays, du budget attribué jusqu'à la pièce
              justificative.
            </p>

            <ul className="mt-10 space-y-6">
              {PROMESSES.map(({ icon: Icon, titre, texte }) => (
                <li key={titre} className="flex gap-4">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-foreground/10">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{titre}</p>
                    <p className="mt-0.5 text-sm text-primary-foreground/60">
                      {texte}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <p className="relative text-xs text-primary-foreground/50">
          Accès réservé aux comptes ouverts par le siège.
        </p>
      </aside>

      {/* Formulaire */}
      <main className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          {/* Reprend l'identité sur mobile, où le panneau est masqué. */}
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Wallet className="h-5 w-5" />
            </div>
            <div className="leading-tight">
              <p className="font-semibold tracking-tight">
                Contrôle budgétaire
              </p>
              <p className="text-xs text-muted-foreground">
                Suivi des dépenses et des justificatifs
              </p>
            </div>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-semibold tracking-tight">Connexion</h2>
            <p className="mt-1.5 text-sm text-muted-foreground">
              Identifiez-vous pour accéder à votre périmètre.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="grid gap-5" noValidate>
            {/* `role="alert"` : l'échec doit être annoncé aux lecteurs d'écran,
                pas seulement apparaître à l'écran. */}
            {error && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
              >
                <Lock className="mt-0.5 h-4 w-4 shrink-0" />
                {error}
              </p>
            )}

            <div className="grid gap-2">
              <Label htmlFor="username">Identifiant</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="prenom.innov"
                autoComplete="username"
                autoFocus
                required
                className="h-10"
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="password">Mot de passe</Label>
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
                  aria-label={
                    visible
                      ? "Masquer le mot de passe"
                      : "Afficher le mot de passe"
                  }
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

            <Button
              type="submit"
              disabled={loading}
              className="mt-1 h-10 w-full"
            >
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Se connecter
            </Button>
          </form>

          <p className="mt-8 text-center text-xs text-muted-foreground">
            Mot de passe oublié ? Contactez un administrateur du siège.
          </p>
        </div>
      </main>
    </div>
  )
}
