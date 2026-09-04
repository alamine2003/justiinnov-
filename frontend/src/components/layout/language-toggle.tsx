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
          <Button variant="ghost" size="icon" aria-label={t("layout.langue_bouton")}>
            <Languages className="h-4 w-4" />
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
