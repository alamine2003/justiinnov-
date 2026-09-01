import { Navigate, Route, Routes } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { AppLayout } from "@/components/layout/app-layout"
import { useAuth } from "@/context/auth"
import { AuditPage } from "@/pages/audit/list"
import { BudgetsPage } from "@/pages/budgets/list"
import { CountriesPage } from "@/pages/countries/list"
import { CountryDetailPage } from "@/pages/countries/detail"
import { DashboardPage } from "@/pages/dashboard"
import { DossierDetailPage } from "@/pages/dossiers/detail"
import { DossiersPage } from "@/pages/dossiers/list"
import { LoginPage } from "@/pages/login"
import { UsersPage } from "@/pages/users/list"
import type { Permissions } from "@/lib/types"

function FullPageLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  )
}

function Protected({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, me, loadingProfile } = useAuth()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  // Attendre le profil évite d'afficher brièvement des actions interdites.
  if (!me || loadingProfile) {
    return <FullPageLoader />
  }
  return <>{children}</>
}

/**
 * Masque une page dont le rôle n'a pas les droits. Purement ergonomique : le
 * backend refuse de toute façon la requête.
 */
function RequirePermission({
  permission,
  children,
}: {
  permission: keyof Permissions
  children: React.ReactNode
}) {
  const { can } = useAuth()
  if (!can(permission)) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <Protected>
            <AppLayout />
          </Protected>
        }
      >
        <Route path="/countries" element={<CountriesPage />} />
        <Route path="/countries/:id" element={<CountryDetailPage />} />
        <Route path="/budgets" element={<BudgetsPage />} />
        <Route path="/" element={<DashboardPage />} />
        <Route path="/dossiers" element={<DossiersPage />} />
        <Route path="/dossiers/:id" element={<DossierDetailPage />} />
        <Route
          path="/audit"
          element={
            <RequirePermission permission="view_audit">
              <AuditPage />
            </RequirePermission>
          }
        />
        <Route
          path="/users"
          element={
            <RequirePermission permission="manage_users">
              <UsersPage />
            </RequirePermission>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
