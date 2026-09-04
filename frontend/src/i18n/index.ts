/**
 * Internationalisation de l'interface : français et anglais.
 *
 * La langue est choisie dans cet ordre : préférence enregistrée dans le
 * navigateur (`justi_lang`), puis langue du navigateur, puis français. Le
 * profil (`GET /api/me/`) peut ensuite imposer la langue enregistrée côté
 * serveur, voir `AuthProvider`.
 *
 * Les libellés qui viennent du serveur (`*_display`, alertes, messages
 * d'erreur) ne sont pas traduits ici : l'API les rend dans la langue de
 * l'en-tête `Accept-Language`, posé par le client HTTP (`lib/api.ts`).
 */
import i18next from "i18next"
import LanguageDetector from "i18next-browser-languagedetector"
import { initReactI18next } from "react-i18next"
import { setApiLanguage } from "@/lib/api"
import { invalidateReferentiel } from "@/lib/referentiel"
import en from "./en.json"
import fr from "./fr.json"

export const LANGUAGES = ["fr", "en"] as const
export type Language = (typeof LANGUAGES)[number]

export const DEFAULT_LANGUAGE: Language = "fr"
export const LANGUAGE_STORAGE_KEY = "justi_lang"

export function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && (LANGUAGES as readonly string[]).includes(value)
}

/** Langue effectivement appliquée, toujours l'une des deux prises en charge. */
export function currentLanguage(): Language {
  const resolved = i18next.resolvedLanguage ?? i18next.language
  return isLanguage(resolved) ? resolved : DEFAULT_LANGUAGE
}

/** Locale `Intl` de la langue courante, pour les dates et les nombres. */
export function currentLocale(): string {
  return currentLanguage() === "en" ? "en-GB" : "fr-FR"
}

function applyLanguage() {
  const language = currentLanguage()
  document.documentElement.lang = language
  document.title = i18next.t("app.titre")
  setApiLanguage(language)
}

void i18next
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { fr: { translation: fr }, en: { translation: en } },
    fallbackLng: DEFAULT_LANGUAGE,
    supportedLngs: [...LANGUAGES],
    load: "languageOnly",
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: ["localStorage"],
    },
    interpolation: { escapeValue: false },
    returnNull: false,
    // Les ressources sont embarquées : `t` est utilisable dès le retour
    // d'`init`, sans attendre un chargement différé.
    initAsync: false,
  })

applyLanguage()

i18next.on("languageChanged", () => {
  applyLanguage()
  // Les listes de référentiel en mémoire portent des libellés serveur dans
  // l'ancienne langue : elles sont rechargées. Les pages, elles, suivent la
  // langue par la clé de `useQuery`.
  invalidateReferentiel()
})

export default i18next
