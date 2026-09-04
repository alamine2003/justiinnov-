import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { apiPatch } from "@/lib/api"
import { currentLanguage, type Language } from "@/i18n"

/**
 * Langue courante et changement de langue.
 *
 * Le choix est enregistré dans le navigateur par le détecteur, puis — pour
 * une session ouverte — sur le profil (`PATCH /api/me/`), afin de retrouver
 * la même langue sur un autre poste. Le serveur peut ne pas encore connaître
 * le champ : son refus n'empêche pas l'interface de changer de langue.
 */
export function useLanguage(options: { persistOnServer?: boolean } = {}) {
  const { i18n } = useTranslation()
  const { persistOnServer = false } = options

  const setLanguage = useCallback(
    async (language: Language) => {
      await i18n.changeLanguage(language)
      if (persistOnServer) {
        try {
          await apiPatch("/me/", { language })
        } catch {
          // Champ absent ou serveur injoignable : la langue reste locale.
        }
      }
    },
    [i18n, persistOnServer],
  )

  return { language: currentLanguage(), setLanguage }
}
