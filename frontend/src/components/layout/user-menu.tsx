import { CircleUserRound, Download, LogOut, Users } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/context/use-auth"
import { useInstallPrompt } from "@/lib/install-prompt"

/**
 * Menu du compte : identité, installation de l'application, déconnexion.
 *
 * L'entrée « Installer l'application » n'apparaît que lorsque le navigateur
 * a signalé que la page est installable (Chrome, Edge) : ailleurs, elle ne
 * mènerait à rien.
 */
export function UserMenu({ onLogout }: { onLogout: () => void }) {
  const { t } = useTranslation()
  const { me } = useAuth()
  const { available, install } = useInstallPrompt()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="sm" aria-label={t("nav.menu_utilisateur")}>
            <CircleUserRound className="h-4 w-4 lg:mr-2" aria-hidden />
            <span className="hidden max-w-40 truncate lg:inline">{me?.username}</span>
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="min-w-56">
        {me && (
          <DropdownMenuLabel className="truncate">
            {me.username} · {me.role_display}
          </DropdownMenuLabel>
        )}
        {/* Un manager rattaché à des équipes ne saisit que pour elles :
            les nommer ici lève toute ambiguïté sur son périmètre. */}
        {me?.teams && me.teams.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5" aria-hidden />
              {t("nav.equipes")}
            </DropdownMenuLabel>
            <ul className="px-1.5 pb-1 text-sm">
              {me.teams.map((team) => (
                <li key={team.id} className="truncate py-0.5">
                  {team.name}
                </li>
              ))}
            </ul>
          </>
        )}
        {available && (
          <DropdownMenuItem onClick={() => void install()}>
            <Download aria-hidden />
            {t("pwa.installer")}
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onLogout}>
          <LogOut aria-hidden />
          {t("nav.deconnexion")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
