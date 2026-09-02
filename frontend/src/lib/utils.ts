import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Formate un montant renvoyé par l'API.
 *
 * Les montants transitent en chaîne pour préserver la précision décimale : la
 * conversion en `number` n'a lieu qu'ici, pour l'affichage.
 */
export function formatAmount(
  value: string | null | undefined,
  currency?: string,
): string {
  if (value === null || value === undefined || value === "") return "—"
  const amount = Number(value)
  if (Number.isNaN(amount)) return "—"
  const formatted = new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount)
  return currency ? `${formatted} ${currency}` : formatted
}

/** Formate un ratio décimal (« 0.8250 ») en pourcentage. */
export function formatRate(value: string | null | undefined): string {
  if (!value) return "—"
  const rate = Number(value)
  if (Number.isNaN(rate)) return "—"
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(rate * 100)} %`
}

/**
 * Formate une date dans le fuseau d'un pays.
 *
 * §6 : les dates sont stockées en UTC, mais une dépense se lit à l'heure du
 * pays où elle a eu lieu. Sans cela, un contrôleur au siège verrait l'heure de
 * son propre fuseau, ce qui fausse le « quand ».
 */
export function formatDateIn(
  value: string | null | undefined,
  timeZone: string | null | undefined,
): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  try {
    return new Intl.DateTimeFormat("fr-FR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: timeZone || undefined,
    }).format(date)
  } catch {
    // Un fuseau inconnu de l'environnement ne doit pas casser l'affichage.
    return formatDate(value)
  }
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}
