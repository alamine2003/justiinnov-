import { Link, NavLink, Outlet, useNavigate } from "react-router-dom"
import {
  FolderOpen,
  Globe,
  LayoutDashboard,
  ListChecks,
  LogOut,
  ScrollText,
  Settings,
  Wallet,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { AppFooter } from "@/components/layout/app-footer"
import { BrandMark } from "@/components/layout/brand-mark"
import { NotificationBell } from "@/components/layout/notification-bell"
import { PasswordNotice } from "@/components/layout/password-notice"
import { useAuth } from "@/context/auth"
import { BRAND } from "@/lib/brand"
import { cn } from "@/lib/utils"

function NavItem({
  to,
  icon: Icon,
  children,
}: {
  to: string
  icon: typeof Globe
  children: React.ReactNode
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "inline-flex items-center rounded-lg px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        )
      }
    >
      <Icon className="mr-2 h-4 w-4" />
      {children}
    </NavLink>
  )
}

export function AppLayout() {
  const { logout, me, can } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  // Un représentant pays n'a qu'un périmètre : l'afficher évite toute
  // ambiguïté sur les données consultées.
  const scope = me?.has_global_scope
    ? "Siège — tous pays"
    : me?.countries.map((c) => c.country_ref ?? c.name).join(", ")

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-card/85 shadow-sm backdrop-blur-md">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-3">
              <BrandMark className="h-10 w-10" />
              <div className="leading-tight">
                <p className="flex items-center gap-1.5 font-semibold tracking-tight text-foreground">
                  {BRAND.name}
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                    v{BRAND.version}
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">{scope}</p>
              </div>
            </Link>
          </div>

          <div className="flex items-center gap-1">
            {/* Aucun menu tant que le mot de passe du siège n'est pas
                remplacé : chaque entrée mènerait à une page que le serveur
                refuse de servir. */}
            {!me?.must_change_password && (
              <>
                <NavItem to="/" icon={LayoutDashboard}>
                  Pilotage
                </NavItem>
                <NavItem to="/dossiers" icon={FolderOpen}>
                  Dossiers
                </NavItem>
                <NavItem to="/registre" icon={ListChecks}>
                  Registre
                </NavItem>
                <NavItem to="/budgets" icon={Wallet}>
                  Budgets
                </NavItem>
                <NavItem to="/countries" icon={Globe}>
                  Pays
                </NavItem>
                {can("view_audit") && (
                  <NavItem to="/audit" icon={ScrollText}>
                    Audit
                  </NavItem>
                )}
                {can("manage_users") && (
                  <NavItem to="/configuration" icon={Settings}>
                    Configuration
                  </NavItem>
                )}
              </>
            )}

            {me && (
              <Badge variant="secondary" className="ml-2 font-normal">
                {me.username} · {me.role_display}
              </Badge>
            )}
            {!me?.must_change_password && <NotificationBell />}
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="mr-2 h-4 w-4" />
              Déconnexion
            </Button>
          </div>
        </div>
      </header>
      {/* `min-h-0 flex-1` maintient le pied de page en bas même sur un écran
          court, sans le coller au contenu sur un écran long. */}
      {/* Tant que le mot de passe du siège n'est pas remplacé, le serveur
          refuse tout : afficher les pages produirait un mur d'erreurs
          derrière la boîte de dialogue. On ne les monte donc pas. */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
        {me?.must_change_password ? <PasswordNotice /> : <Outlet />}
      </main>
      <AppFooter />
    </div>
  )
}
