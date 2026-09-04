import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const LOCALE = "fr-FR"

// Les formateurs `Intl` coûtent cher à construire ; un tableau de cinquante
// lignes en créait plusieurs centaines. Ils sont réutilisés par options.
const numberFormats = new Map<string, Intl.NumberFormat>()
const dateFormats = new Map<string, Intl.DateTimeFormat>()

function numberFormat(options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = JSON.stringify(options)
  let format = numberFormats.get(key)
  if (!format) {
    format = new Intl.NumberFormat(LOCALE, options)
    numberFormats.set(key, format)
  }
  return format
}

function dateFormat(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = JSON.stringify(options)
  let format = dateFormats.get(key)
  if (!format) {
    format = new Intl.DateTimeFormat(LOCALE, options)
    dateFormats.set(key, format)
  }
  return format
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
  options: { maxFractionDigits?: number } = {},
): string {
  if (value === null || value === undefined || value === "") return "—"
  const amount = Number(value)
  if (Number.isNaN(amount)) return "—"
  const formatted = numberFormat({
    minimumFractionDigits: 0,
    maximumFractionDigits: options.maxFractionDigits ?? 2,
  }).format(amount)
  return currency ? `${formatted} ${currency}` : formatted
}

/** Formate un ratio décimal (« 0.8250 ») en pourcentage. */
export function formatRate(value: string | null | undefined): string {
  if (!value) return "—"
  const rate = Number(value)
  if (Number.isNaN(rate)) return "—"
  return `${numberFormat({ maximumFractionDigits: 1 }).format(rate * 100)} %`
}

/**
 * Lit une date « AAAA-MM-JJ » comme un jour local.
 *
 * `new Date("2026-03-15")` est interprété en UTC : à l'ouest de Greenwich, le
 * 15 devenait le 14 à l'affichage. Une date sans heure est un jour calendaire,
 * pas un instant.
 */
export function parseLocalDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const [, year, month, day] = match
  const date = new Date(Number(year), Number(month) - 1, Number(day))
  if (
    date.getFullYear() !== Number(year) ||
    date.getMonth() !== Number(month) - 1 ||
    date.getDate() !== Number(day)
  ) {
    return null
  }
  return date
}

/** Jour calendaire (« 15 mars 2026 ») pour une date sans heure. */
export function formatDay(value: string | null | undefined): string {
  if (!value) return "—"
  const date = parseLocalDate(value) ?? new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return dateFormat({ day: "2-digit", month: "short", year: "numeric" }).format(date)
}

/** La date du jour au format « AAAA-MM-JJ », en heure locale. */
export function todayIso(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  const day = String(now.getDate()).padStart(2, "0")
  return `${now.getFullYear()}-${month}-${day}`
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
    return dateFormat({
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
  return dateFormat({
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}

/** Décalage, en minutes, d'un fuseau par rapport à UTC à un instant donné. */
function offsetMinutes(date: Date, timeZone: string): number {
  const parts = dateFormat({
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(date)
  const read = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value ?? 0)
  const asUtc = Date.UTC(
    read("year"),
    read("month") - 1,
    read("day"),
    read("hour"),
    read("minute"),
    read("second"),
  )
  return Math.round((asUtc - date.getTime()) / 60_000)
}

/**
 * Convertit un instant en valeur d'`<input type="datetime-local">` lue dans
 * le fuseau du pays.
 *
 * Le champ n'a pas de notion de fuseau : sans conversion explicite, un
 * contrôleur au siège saisirait l'heure de Paris pour une dépense de Lomé.
 */
export function toCountryLocalInput(
  iso: string,
  timeZone: string | null | undefined,
): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  let shifted: Date
  try {
    shifted = new Date(
      date.getTime() + (timeZone ? offsetMinutes(date, timeZone) : -date.getTimezoneOffset()) * 60_000,
    )
  } catch {
    shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  }
  return shifted.toISOString().slice(0, 16)
}

/**
 * Lit une valeur d'`<input type="datetime-local">` comme une heure du pays et
 * renvoie l'instant correspondant en ISO 8601 (UTC).
 */
export function fromCountryLocalInput(
  local: string,
  timeZone: string | null | undefined,
): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(local)
  if (!match) return null
  const [, year, month, day, hour, minute, second] = match
  if (!timeZone) {
    const localDate = new Date(
      Number(year), Number(month) - 1, Number(day),
      Number(hour), Number(minute), Number(second ?? 0),
    )
    return Number.isNaN(localDate.getTime()) ? null : localDate.toISOString()
  }
  const naive = Date.UTC(
    Number(year), Number(month) - 1, Number(day),
    Number(hour), Number(minute), Number(second ?? 0),
  )
  try {
    // Le décalage dépend de l'instant (heure d'été) : une seconde passe le
    // corrige lorsque la première estimation tombe de l'autre côté du
    // changement d'heure.
    let instant = naive - offsetMinutes(new Date(naive), timeZone) * 60_000
    instant = naive - offsetMinutes(new Date(instant), timeZone) * 60_000
    return new Date(instant).toISOString()
  } catch {
    return new Date(naive).toISOString()
  }
}

/**
 * Normalise une saisie décimale « à la française » (« 1 234,56 ») en chaîne
 * acceptée par le serveur (« 1234.56»). Renvoie `null` si la saisie n'est
 * pas un nombre.
 */
export function normalizeDecimal(input: string): string | null {
  const compact = input.replace(/[\s  ]/g, "").replace(",", ".")
  if (compact === "") return null
  if (!/^-?\d+(\.\d+)?$/.test(compact)) return null
  return compact
}

/** Accorde un nom en nombre : « 1 dossier », « 3 dossiers ». */
export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${numberFormat({}).format(count)} ${count > 1 ? plural : singular}`
}
