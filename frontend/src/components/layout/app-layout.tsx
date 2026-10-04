import { useState } from "react"
import type { ComponentType } from "react"
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import {
  Activity,
  Briefcase,
  Download,
  Globe,
  Info,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
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
import { BackButton } from "@/components/layout/back-button"
import { BrandLogo } from "@/components/layout/brand-logo"
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

/** Le choix de replier le menu, propre à ce navigateur. */
const CLE_REPLI = "justi_menu_replie"

function lireRepli(): boolean {
  try {
    return localStorage.getItem(CLE_REPLI) === "1"
  } catch {
    // Stockage refusé (navigation privée, données bloquées) : menu déplié.
    return false
  }
}

function ecrireRepli(replie: boolean) {
  try {
    localStorage.setItem(CLE_REPLI, replie ? "1" : "0")
  } catch {
    // Le choix vaut alors pour la page ouverte, pas au-delà.
  }
}

interface Entree {
  to: string
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>
  label: string
}

interface Groupe {
  cle: string
  titre: string
  entrees: Entree[]
}

function NavItem({
  entree,
  replie,
  onNavigate,
}: {
  entree: Entree
  /** Menu replié : icône seule, le libellé reste le nom accessible. */
  replie: boolean
  onNavigate?: () => void
}) {
  const { to, icon: Icon, label } = entree
  return (
    <NavLink
      to={to}
      end={to === "/"}
      onClick={onNavigate}
      title={replie ? label : undefined}
      className={({ isActive }) =>
        cn(
          "flex items-center rounded-lg py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          replie ? "justify-center px-2" : "px-3",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        )
      }
    >
      <Icon className={cn("h-4 w-4 shrink-0", !replie && "mr-3")} aria-hidden />
      <span className={replie ? "sr-only" : "truncate"}>{label}</span>
    </NavLink>
  )
}

/** Les entrées, par groupe ; un groupe replié ne garde qu'un filet. */
function Navigation({
  groupes,
  replie,
  onNavigate,
}: {
  groupes: Groupe[]
  replie: boolean
  onNavigate?: () => void
}) {
  return (
    <>
      {groupes.map((groupe, index) => (
        <div key={groupe.cle} className={cn(index > 0 && "mt-4")}>
          {replie ? (
            index > 0 && <div aria-hidden className="mx-2 mb-4 border-t border-border/60" />
          ) : (
            <p className="mb-1 px-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {groupe.titre}
            </p>
          )}
          <div className="flex flex-col gap-0.5">
            {groupe.entrees.map((entree) => (
              <NavItem key={entree.to} entree={entree} replie={replie} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      ))}
    </>
  )
}

export function AppLayout() {
  const { t } = useTranslation()
  const { logout, me, can } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [replie, setReplie] = useState(lireRepli)
  const { available: installable, install } = useInstallPrompt()
  const notice = (location.state as { notice?: string } | null)?.notice

  const handleLogout = async () => {
    await logout()
    navigate("/login")
  }

  // Un manager n'a qu'un périmètre, son pays :
  // l'afficher évite toute ambiguïté sur les données consultées.
  const scope = me?.has_global_scope
    ? t("commun.siege_tous_pays")
    : me?.countries.map((c) => c.country_ref ?? c.name).join(", ")

  // Aucun menu tant que le mot de passe du siège n'est pas remplacé ni la
  // double authentification enrôlée : chaque entrée mènerait à une page que
  // le serveur refuse de servir.
  const closed = platformClosed(me)
  const groupes: Groupe[] = closed
    ? []
    : [
        {
          cle: "suivi",
          titre: t("nav.groupe.suivi"),
          entrees: [
            { to: "/", icon: LayoutDashboard, label: t("nav.pilotage") },
            { to: "/projets", icon: Briefcase, label: t("nav.projets") },
            { to: "/registre", icon: ListChecks, label: t("nav.registre") },
          ],
        },
        {
          cle: "budget",
          titre: t("nav.groupe.budget"),
          entrees: [
            { to: "/budgets", icon: Wallet, label: t("nav.budgets") },
            { to: "/countries", icon: Globe, label: t("nav.pays") },
          ],
        },
        {
          cle: "controle",
          titre: t("nav.groupe.controle"),
          entrees: can("audit.read")
            ? [{ to: "/audit", icon: ScrollText, label: t("nav.audit") }]
            : [],
        },
        {
          cle: "administration",
          titre: t("nav.groupe.administration"),
          entrees: can("configuration.manage")
            ? [{ to: "/configuration", icon: Settings, label: t("nav.configuration") }]
            : [],
        },
      ].filter((groupe) => groupe.entrees.length > 0)
  const avecMenu = groupes.length > 0

  const basculerRepli = () => {
    setReplie((avant) => {
      ecrireRepli(!avant)
      return !avant
    })
  }

  return (
    <div className="flex min-h-screen bg-background">
      {/* Dès `lg`, la navigation est une barre latérale : les sept entrées du
          siège y tiennent avec leur libellé, groupées, et la liste peut
          s'allonger. Repliée, elle n'est plus qu'une bande d'icônes. Sous
          `lg`, elle passe dans le panneau du menu ☰. */}
      {avecMenu && (
        <aside
          className={cn(
            "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border/60 bg-card lg:flex",
            replie ? "w-16" : "w-60",
          )}
        >
          <Link
            to="/"
            aria-label={BRAND.name}
            className={cn(
              "flex h-16 shrink-0 items-center gap-2 border-b border-border/60 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              replie ? "justify-center" : "px-5",
            )}
          >
            {replie ? (
              <BrandMark className="h-7 w-7" />
            ) : (
              <>
                {/* Le logo porte le nom : il n'est pas répété en texte. */}
                <BrandLogo className="h-7 w-auto" />
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                  v{BRAND.version}
                </span>
              </>
            )}
          </Link>
          <nav
            aria-label={t("nav.principale")}
            className={cn("flex-1 overflow-y-auto py-4", replie ? "px-2" : "px-3")}
          >
            <Navigation groupes={groupes} replie={replie} />
          </nav>
          <div className="shrink-0 border-t border-border/60 p-2">
            <Button
              variant="ghost"
              size="sm"
              className={cn("w-full text-muted-foreground", replie ? "justify-center" : "justify-start")}
              aria-expanded={!replie}
              aria-label={replie ? t("nav.deplier_menu") : t("nav.reduire_menu")}
              title={replie ? t("nav.deplier_menu") : undefined}
              onClick={basculerRepli}
            >
              {replie ? (
                <PanelLeftOpen className="h-4 w-4" aria-hidden />
              ) : (
                <>
                  <PanelLeftClose className="mr-2 h-4 w-4" aria-hidden />
                  {t("nav.reduire_menu")}
                </>
              )}
            </Button>
          </div>
        </aside>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 border-b border-border/60 bg-card/85 shadow-sm backdrop-blur-md">
          <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              {/* Le logo vit dans la barre latérale dès `lg` ; l'en-tête le
                  garde en dessous, ou quand la plateforme est fermée. */}
              <Link
                to="/"
                aria-label={BRAND.name}
                className={cn(
                  "flex shrink-0 items-center rounded-lg text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  avecMenu && "lg:hidden",
                )}
              >
                <BrandLogo className="h-7 w-auto" />
              </Link>
              {/* Le périmètre reste sous les yeux : il dit quelles données on lit. */}
              <div className="min-w-0 leading-tight">
                <span
                  className={cn(
                    "rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground",
                    avecMenu && "lg:hidden",
                  )}
                >
                  v{BRAND.version}
                </span>
                <p className="truncate text-xs text-muted-foreground lg:text-sm">{scope}</p>
              </div>
            </div>

            <div className="flex items-center gap-1">
              {!closed && <NotificationBell />}
              <LanguageToggle persistOnServer />
              <ThemeToggle />
              <div className="hidden lg:block">
                <UserMenu onLogout={() => void handleLogout()} />
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
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
              <SheetTitle className="flex items-center gap-2">
                <BrandMark className="h-6 w-6" />
                {BRAND.name}
              </SheetTitle>
              <SheetDescription>
                {me ? [me.username, me.role_display].filter(Boolean).join(" · ") : scope}
              </SheetDescription>
            </SheetHeader>
            <nav aria-label={t("nav.principale")} className="px-4">
              <Navigation groupes={groupes} replie={false} onNavigate={() => setMenuOpen(false)} />
            </nav>
            {/* Les entrées du menu du compte, que le panneau remplace sous `lg`. */}
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
          {/* Retour en haut de chaque page, sauf l'accueil ; pas quand la
              plateforme est fermée — il n'y a alors nulle part où revenir. */}
          {!closed && <BackButton />}
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
    </div>
  )
}
