import { currentLocale } from "@/i18n"

/** Mois de l'exercice, 1 à 12, tels que les exports les attendent. */
export const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const

/** Nom du mois dans la langue courante, initiale en capitale. */
export function monthName(month: number): string {
  const locale = currentLocale()
  const nom = new Intl.DateTimeFormat(locale, { month: "long" }).format(
    new Date(2000, month - 1, 1),
  )
  return nom.charAt(0).toLocaleUpperCase(locale) + nom.slice(1)
}
