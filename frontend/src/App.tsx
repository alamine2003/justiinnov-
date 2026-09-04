import { Suspense, lazy, type ReactNode } from "react"
import { Navigate, Route, Routes, useLocation } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { AppLayout } from "@/components/layout/app-layout"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import { useAuth } from "@/context/use-auth"
import type { Permissions } from "@/lib/types"

// Chaque page est un fichier chargé à la première visite : l'écran de
// connexion n'a pas à embarquer le back-office.
const LoginPage = lazy(() => import("@/pages/login").then((m) => ({ default: m.LoginPage })))
const DashboardPage = lazy(() => import("@/pages/dashboard").then((m) => ({ default: m.DashboardPage })))
const DossiersPage = lazy(() => import("@/pages/dossiers/list").then((m) => ({ default: m.DossiersPage })))
const DossierDetailPage = lazy(() => import("@/pages/dossiers/detail").then((m) => ({ default: m.DossierDetailPage })))
const RegisterPage = lazy(() => import("@/pages/register").then((m) => ({ default: m.RegisterPage })))
const BudgetsPage = lazy(() => import("@/pages/budgets/list").then((m) => ({ default: m.BudgetsPage })))
const CountriesPage = lazy(() => import("@/pages/countries/list").then((m) => ({ default: m.CountriesPage })))
const CountryDetailPage = lazy(() => import("@/pages/countries/detail").then((m) => ({ default: m.CountryDetailPage })))
const AuditPage = lazy(() => import("@/pages/audit/list").then((m) => ({ default: m.AuditPage })))
const ConfigurationPage = lazy(() => import("@/pages/configuration").then((m) => ({ default: m.ConfigurationPage })))
const PasswordPage = lazy(() => import("@/pages/password").then((m) => ({ default: m.PasswordPage })))

export function FullPageLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center" aria-busy="true">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <span className="sr-only">Chargement…</span>
    </div>
  )
}

/** Chemin de l'écran de remplacement du mot de passe provisoire. */
export const PASSWORD_PATH = "/mot-de-passe"

function Protected({ children }: { children: ReactNode }) {
  const { isAuthenticated, me, loadingProfile, profileError, refreshProfile } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  if (!me && profileError && !loadingProfile) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div role="alert" className="max-w-md space-y-3 rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
          <p>{profileError}</p>
          <button
            type="button"
            className="underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => void refreshProfile().catch(() => {})}
          >
            Réessayer
          </button>
        </div>
      </div>
    )
  }
  // Attendre le profil évite d'afficher brièvement des actions interdites.
  if (!me || loadingProfile) {
    return <FullPageLoader />
  }
  // Un mot de passe provisoire ne mène qu'à l'écran qui le remplace : le
  // serveur refuse tout le reste, chaque page serait un mur d'erreurs.
  if (me.must_change_password && location.pathname !== PASSWORD_PATH) {
    return <Navigate to={PASSWORD_PATH} replace />
  }
  return <>{children}</>
}

/**
 * Masque une page dont le rôle n'a pas les droits. Purement ergonomique : le
 * backend refuse de toute façon la requête. Le message est porté par l'état
 * de navigation, pour que le tableau de bord explique la redirection.
 */
function RequirePermission({
  permission,
  children,
}: {
  permission: keyof Permissions
  children: ReactNode
}) {
  const { can } = useAuth()
  if (!can(permission)) {
    return (
      <Navigate
        to="/"
        replace
        state={{ notice: "Page réservée au siège : vous avez été ramené au tableau de bord." }}
      />
    )
  }
  return <>{children}</>
}

function PasswordRoute() {
  const { me } = useAuth()
  if (!me?.must_change_password) {
    return <Navigate to="/" replace />
  }
  return <PasswordPage />
}

export default function App() {
  return (
    <Suspense fallback={<FullPageLoader />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <Protected>
              <ErrorBoundary>
                <AppLayout />
              </ErrorBoundary>
            </Protected>
          }
        >
          <Route path={PASSWORD_PATH} element={<PasswordRoute />} />
          <Route path="/countries" element={<CountriesPage />} />
          <Route path="/countries/:id" element={<CountryDetailPage />} />
          <Route path="/budgets" element={<BudgetsPage />} />
          <Route path="/" element={<DashboardPage />} />
          <Route path="/dossiers" element={<DossiersPage />} />
          <Route path="/dossiers/:id" element={<DossierDetailPage />} />
          <Route path="/registre" element={<RegisterPage />} />
          <Route
            path="/audit"
            element={
              <RequirePermission permission="view_audit">
                <AuditPage />
              </RequirePermission>
            }
          />
          <Route
            path="/configuration"
            element={
              <RequirePermission permission="manage_users">
                <ConfigurationPage />
              </RequirePermission>
            }
          />
        </Route>
        {/* La page Comptes a été absorbée par le back-office : les liens et
            favoris existants doivent continuer de mener quelque part. */}
        <Route
          path="/users"
          element={<Navigate to="/configuration?onglet=utilisateurs" replace />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
