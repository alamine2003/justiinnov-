import { Link, NavLink, Outlet, useNavigate } from "react-router-dom"
import { FolderOpen, Globe, LogOut, ScrollText, Users, Wallet } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { PasswordNotice } from "@/components/layout/password-notice"
import { useAuth } from "@/context/auth"
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
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-card/85 shadow-sm backdrop-blur-md">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <Link to="/countries" className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-md shadow-primary/15">
                <Globe className="h-5 w-5" />
              </div>
              <div className="leading-tight">
                <p className="font-semibold tracking-tight text-foreground">
                  Contrôle budgétaire
                </p>
                <p className="text-xs text-muted-foreground">{scope}</p>
              </div>
            </Link>
          </div>

          <div className="flex items-center gap-1">
            <NavItem to="/dossiers" icon={FolderOpen}>
              Dossiers
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
              <NavItem to="/users" icon={Users}>
                Comptes
              </NavItem>
            )}

            {me && (
              <Badge variant="secondary" className="ml-2 font-normal">
                {me.username} · {me.role_display}
              </Badge>
            )}
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="mr-2 h-4 w-4" />
              Déconnexion
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl px-6 py-8">
        <PasswordNotice />
        <Outlet />
      </main>
    </div>
  )
}
