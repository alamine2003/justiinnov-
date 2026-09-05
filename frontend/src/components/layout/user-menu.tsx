import { Activity, CircleUserRound, Download, LogOut, ShieldCheck, Users } from "lucide-react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/context/use-auth"
import { TOTP_PATH } from "@/lib/accounts"
import { useInstallPrompt } from "@/lib/install-prompt"
import { STATUS_TONES } from "@/lib/status-styles"

/**
 * Supervision (Grafana), servie par Caddy sous le même domaine : le chemin
 * est relatif à l'origine, quel que soit l'environnement.
 */
export const SUPERVISION_PATH = "/grafana/"

/**
 * Menu du compte : identité, double authentification, supervision,
 * installation de l'application, déconnexion.
 *
 * L'entrée « Installer l'application » n'apparaît que lorsque le navigateur
 * a signalé que la page est installable (Chrome, Edge) : ailleurs, elle ne
 * mènerait à rien. « Activer la double authentification » n'apparaît qu'à
 * un compte qui ne l'a pas encore enrôlée, et « Supervision » aux
 * administrateurs, seuls à avoir un compte Grafana.
 */
export function UserMenu({ onLogout }: { onLogout: () => void }) {
  const { t } = useTranslation()
  const { me, can } = useAuth()
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
        {/* Un libellé de menu vit dans un groupe : base-ui l'exige. */}
        {me && (
          <DropdownMenuGroup>
            <DropdownMenuLabel className="flex items-center gap-2">
              <span className="truncate">
                {[me.username, me.role_display].filter(Boolean).join(" · ")}
              </span>
              {me.totp_confirmed === true && (
                <Badge className={STATUS_TONES.SUCCES}>{t("nav.totp_active")}</Badge>
              )}
            </DropdownMenuLabel>
          </DropdownMenuGroup>
        )}
        {/* Un manager rattaché à des équipes ne saisit que pour elles :
            les nommer ici lève toute ambiguïté sur son périmètre. */}
        {me?.teams && me.teams.length > 0 && (
          <DropdownMenuGroup>
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
          </DropdownMenuGroup>
        )}
        {/* Absent sur un serveur qui ignore la 2FA : rien à proposer. */}
        {me?.totp_confirmed === false && (
          <DropdownMenuItem
            render={
              <Link to={TOTP_PATH}>
                <ShieldCheck aria-hidden />
                {t("nav.activer_2fa")}
              </Link>
            }
          />
        )}
        {/* Nouvel onglet : Grafana a sa propre session, l'application garde
            la sienne. Ce n'est pas un droit mais un réglage de déploiement :
            sans Grafana derrière Caddy, le lien mènerait à un 404. */}
        {can("manage_users") && me?.supervision === true && (
          <DropdownMenuItem
            render={
              <a href={SUPERVISION_PATH} target="_blank" rel="noopener noreferrer">
                <Activity aria-hidden />
                {t("nav.supervision")}
              </a>
            }
          />
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
