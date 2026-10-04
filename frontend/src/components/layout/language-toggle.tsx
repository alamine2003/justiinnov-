import { Languages } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { LANGUAGES, isLanguage } from "@/i18n"
import { useLanguage } from "@/i18n/use-language"

/**
 * Sélecteur de langue, jumeau du sélecteur de thème.
 *
 * `persistOnServer` : dans l'application, le choix est aussi enregistré sur
 * le profil ; sur l'écran de connexion, il n'y a pas encore de session.
 */
export function LanguageToggle({ persistOnServer = false }: { persistOnServer?: boolean }) {
  const { t } = useTranslation()
  const { language, setLanguage } = useLanguage({ persistOnServer })

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          // Le code de la langue courante à côté de l'icône : seule, elle se
          // reconnaissait mal. Le nom accessible reste celui du bouton.
          // Le nom accessible contient le texte visible (WCAG 2.5.3) : une
          // commande vocale « cliquer FR » trouve le bouton.
          <Button
            variant="ghost"
            size="sm"
            className="gap-1 px-2"
            aria-label={`${language.toUpperCase()} — ${t("layout.langue_bouton")}`}
          >
            <Languages className="h-4 w-4" aria-hidden />
            <span aria-hidden className="text-xs font-medium">
              {language.toUpperCase()}
            </span>
          </Button>
        }
      />
      <DropdownMenuContent align="end">
        {/* Un groupe radio : la langue courante est annoncée comme cochée. */}
        <DropdownMenuRadioGroup
          value={language}
          onValueChange={(valeur) => {
            if (isLanguage(valeur)) void setLanguage(valeur)
          }}
        >
          {LANGUAGES.map((valeur) => (
            <DropdownMenuRadioItem key={valeur} value={valeur} closeOnClick lang={valeur}>
              {t(`libelles.langue.${valeur}`)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
