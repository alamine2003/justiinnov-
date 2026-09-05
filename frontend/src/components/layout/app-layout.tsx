import { useState } from "react"
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import {
  Activity,
  Download,
  FolderOpen,
  Globe,
  Info,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  ScrollText,
  Settings,
  ShieldCheck,
  Wallet,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { AppFooter } from "@/components/layout/app-footer"
import { BrandMark } from "@/components/layout/brand-mark"
import { LanguageToggle } from "@/components/layout/language-toggle"
import { NotificationBell } from "@/components/layout/notification-bell"
import { ThemeToggle } from "@/components/layout/theme-toggle"
import { SUPERVISION_PATH, UserMenu } from "@/components/layout/user-menu"
import { useAuth } from "@/context/use-auth"
import { TOTP_PATH, platformClosed } from "@/lib/accounts"
import { BRAND } from "@/lib/brand"
import { useInstallPrompt } from "@/lib/install-prompt"
import { cn } from "@/lib/utils"

function NavItem({
  to,
  icon: Icon,
  children,
  onNavigate,
}: {
  to: string
  icon: typeof Globe
  children: React.ReactNode
  onNavigate?: () => void
}) {
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "inline-flex items-center rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        )
      }
    >
      <Icon className="mr-2 h-4 w-4" aria-hidden />
      {children}
    </NavLink>
  )
}

export function AppLayout() {
  const { t } = useTranslation()
  const { logout, me, can } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const { available: installable, install } = useInstallPrompt()
  const notice = (location.state as { notice?: string } | null)?.notice

  const handleLogout = async () => {
    await logout()
    navigate("/login")
  }

  // Un manager, ou un DM/DF restreint à des pays, n'a qu'un périmètre :
  // l'afficher évite toute ambiguïté sur les données consultées.
  const scope = me?.has_global_scope
    ? t("commun.siege_tous_pays")
    : me?.countries.map((c) => c.country_ref ?? c.name).join(", ")

  // Aucun menu tant que le mot de passe du siège n'est pas remplacé ni la
  // double authentification enrôlée : chaque entrée mènerait à une page que
  // le serveur refuse de servir.
  const closed = platformClosed(me)
  const navigation = closed ? null : (
    <>
      <NavItem to="/" icon={LayoutDashboard} onNavigate={() => setMenuOpen(false)}>
        {t("nav.pilotage")}
      </NavItem>
      <NavItem to="/dossiers" icon={FolderOpen} onNavigate={() => setMenuOpen(false)}>
        {t("nav.dossiers")}
      </NavItem>
      <NavItem to="/registre" icon={ListChecks} onNavigate={() => setMenuOpen(false)}>
        {t("nav.registre")}
      </NavItem>
      <NavItem to="/budgets" icon={Wallet} onNavigate={() => setMenuOpen(false)}>
        {t("nav.budgets")}
      </NavItem>
      <NavItem to="/countries" icon={Globe} onNavigate={() => setMenuOpen(false)}>
        {t("nav.pays")}
      </NavItem>
      {can("audit.read") && (
        <NavItem to="/audit" icon={ScrollText} onNavigate={() => setMenuOpen(false)}>
          {t("nav.audit")}
        </NavItem>
      )}
      {can("configuration.manage") && (
        <NavItem to="/configuration" icon={Settings} onNavigate={() => setMenuOpen(false)}>
          {t("nav.configuration")}
        </NavItem>
      )}
    </>
  )

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-card/85 shadow-sm backdrop-blur-md">
        <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
          <Link
            to="/"
            className="flex min-w-0 items-center gap-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <BrandMark className="h-10 w-10 shrink-0" />
            <div className="min-w-0 leading-tight">
              <p className="flex items-center gap-1.5 font-semibold tracking-tight text-foreground">
                {BRAND.name}
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                  v{BRAND.version}
                </span>
              </p>
              <p className="truncate text-xs text-muted-foreground">{scope}</p>
            </div>
          </Link>

          {/* Sous `md`, les sept entrées ne tiennent pas : elles passent dans
              un panneau latéral, pour que la page ne défile jamais
              horizontalement. */}
          <nav aria-label={t("nav.principale")} className="hidden items-center gap-1 md:flex">
            {navigation}
          </nav>

          <div className="flex items-center gap-1">
            {!closed && <NotificationBell />}
            <LanguageToggle persistOnServer />
            <ThemeToggle />
            <div className="hidden md:block">
              <UserMenu onLogout={() => void handleLogout()} />
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label={t("nav.ouvrir_menu")}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>

      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="left" className="w-72">
          <SheetHeader>
            <SheetTitle>{BRAND.name}</SheetTitle>
            <SheetDescription>
              {me ? [me.username, me.role_display].filter(Boolean).join(" · ") : scope}
            </SheetDescription>
          </SheetHeader>
          <nav aria-label={t("nav.principale")} className="flex flex-col gap-1 px-4">
            {navigation}
          </nav>
          {/* Les entrées du menu du compte, que le menu replié remplace sous `md`. */}
          <div className="mt-auto space-y-2 px-4 pb-6">
            {!closed && me?.totp_confirmed === false && (
              <Button
                variant="ghost"
                className="w-full"
                nativeButton={false}
                render={<Link to={TOTP_PATH} onClick={() => setMenuOpen(false)} />}
              >
                <ShieldCheck className="mr-2 h-4 w-4" aria-hidden />
                {t("nav.activer_2fa")}
              </Button>
            )}
            {!closed && can("configuration.manage") && me?.supervision === true && (
              <Button
                variant="ghost"
                className="w-full"
                nativeButton={false}
                render={
                  <a
                    href={SUPERVISION_PATH}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={t("nav.supervision")}
                  />
                }
              >
                <Activity className="mr-2 h-4 w-4" aria-hidden />
                {t("nav.supervision")}
              </Button>
            )}
            {installable && (
              <Button variant="ghost" className="w-full" onClick={() => void install()}>
                <Download className="mr-2 h-4 w-4" aria-hidden />
                {t("pwa.installer")}
              </Button>
            )}
            <Button variant="outline" className="w-full" onClick={() => void handleLogout()}>
              <LogOut className="mr-2 h-4 w-4" aria-hidden />
              {t("nav.deconnexion")}
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      {/* `min-h-0 flex-1` maintient le pied de page en bas même sur un écran
          court, sans le coller au contenu sur un écran long. */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6">
        {notice && (
          <Alert className="mb-6">
            <Info className="h-4 w-4" />
            <AlertDescription>{notice}</AlertDescription>
          </Alert>
        )}
        <Outlet />
      </main>
      <AppFooter />
    </div>
  )
}
