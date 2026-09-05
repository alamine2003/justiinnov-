import { afterEach, describe, expect, it } from "vitest"
import i18n from "@/i18n"

import {
  formatAmount,
  formatDate,
  formatDateIn,
  formatDay,
  formatRate,
  fromCountryLocalInput,
  normalizeDecimal,
  parseLocalDate,
  pluralize,
  toCountryLocalInput,
} from "./utils"

/**
 * `Intl` sépare les milliers par une espace fine insécable, dont le point de
 * code a varié selon les versions de Node. Comparer sur une espace ordinaire
 * rend le test indépendant de cette variation.
 */
const normalise = (value: string) => value.replace(/[\s  ]/g, " ")

describe("formatAmount", () => {
  it("formate un montant transmis en chaîne", () => {
    // Les montants transitent en chaîne pour préserver la précision décimale.
    expect(normalise(formatAmount("1234567.89"))).toBe("1 234 567,89")
  })

  it("accole la devise quand elle est fournie", () => {
    expect(normalise(formatAmount("1000", "XOF"))).toBe("1 000 XOF")
  })

  it("distingue un montant nul d'une valeur absente", () => {
    expect(formatAmount("0")).toBe("0")
    expect(formatAmount(null)).toBe("—")
    expect(formatAmount(undefined)).toBe("—")
    expect(formatAmount("")).toBe("—")
  })

  it("ne prétend pas formater ce qui n'est pas un nombre", () => {
    expect(formatAmount("abc")).toBe("—")
  })

  it("garde les décimales d'un taux de change quand on le lui demande", () => {
    expect(normalise(formatAmount("655.957", undefined, { maxFractionDigits: 6 }))).toBe("655,957")
  })

  it("réutilise le même formateur pour les mêmes options", () => {
    // Un tableau de cinquante lignes ne doit pas construire cinquante
    // formateurs : le résultat doit rester identique d'un appel à l'autre.
    expect(formatAmount("12.5")).toBe(formatAmount("12.5"))
  })
})

describe("formatRate", () => {
  it("présente un ratio décimal en pourcentage", () => {
    expect(normalise(formatRate("0.8333"))).toBe("83,3 %")
    expect(normalise(formatRate("1"))).toBe("100 %")
  })

  it("rend un tiret quand le taux n'est pas calculable", () => {
    // Le serveur renvoie null lorsque le dénominateur est nul.
    expect(formatRate(null)).toBe("—")
  })
})

describe("formatDate", () => {
  it("rend un tiret sur une date invalide plutôt que « Invalid Date »", () => {
    expect(formatDate("pas-une-date")).toBe("—")
    expect(formatDate(null)).toBe("—")
  })

  it("formate une date ISO", () => {
    expect(formatDate("2026-03-15T10:00:00Z")).toMatch(/2026/)
  })
})

describe("parseLocalDate", () => {
  it("lit une date sans heure comme un jour local, pas comme minuit UTC", () => {
    const date = parseLocalDate("2026-03-15")

    expect(date?.getFullYear()).toBe(2026)
    expect(date?.getMonth()).toBe(2)
    expect(date?.getDate()).toBe(15)
    expect(date?.getHours()).toBe(0)
  })

  it("refuse une date impossible ou mal formée", () => {
    expect(parseLocalDate("2026-02-30")).toBeNull()
    expect(parseLocalDate("15/03/2026")).toBeNull()
  })
})

describe("formatDay", () => {
  it("affiche le bon jour quel que soit le fuseau du lecteur", () => {
    expect(formatDay("2026-03-15")).toMatch(/15/)
    expect(formatDay("2026-03-15")).toMatch(/2026/)
  })

  it("rend un tiret sur une valeur absente ou invalide", () => {
    expect(formatDay(null)).toBe("—")
    expect(formatDay("n'importe quoi")).toBe("—")
  })
})

describe("formatDateIn", () => {
  const midiUTC = "2026-03-15T12:00:00Z"

  it("affiche l'heure du pays, pas celle du lecteur", () => {
    // Abidjan est à UTC+0, Nairobi à UTC+3 : la même instant se lit
    // différemment selon le pays où la dépense a eu lieu.
    expect(formatDateIn(midiUTC, "Africa/Abidjan")).toContain("12:00")
    expect(formatDateIn(midiUTC, "Africa/Nairobi")).toContain("15:00")
  })

  it("retombe sur le fuseau du navigateur si aucun n'est fourni", () => {
    expect(formatDateIn(midiUTC, null)).toBe(formatDate(midiUTC))
  })

  it("ne casse pas l'affichage sur un fuseau inconnu", () => {
    expect(formatDateIn(midiUTC, "Mars/Olympus_Mons")).toBe(formatDate(midiUTC))
  })

  it("rend un tiret sur une date absente ou invalide", () => {
    expect(formatDateIn(null, "Africa/Lome")).toBe("—")
    expect(formatDateIn("n'importe quoi", "Africa/Lome")).toBe("—")
  })
})

describe("conversion datetime-local ↔ fuseau du pays", () => {
  it("présente l'heure du pays dans le champ", () => {
    expect(toCountryLocalInput("2026-03-15T07:00:00Z", "Africa/Nairobi")).toBe("2026-03-15T10:00")
    expect(toCountryLocalInput("2026-03-15T07:00:00Z", "Africa/Abidjan")).toBe("2026-03-15T07:00")
  })

  it("lit la saisie comme une heure du pays", () => {
    // 10 h à Nairobi (UTC+3), c'est 7 h UTC. Sans conversion, un contrôleur à
    // Paris enregistrerait 10 h de Paris — une heure qui n'existe pas sur la
    // pièce.
    expect(fromCountryLocalInput("2026-03-15T10:00", "Africa/Nairobi")).toBe("2026-03-15T07:00:00.000Z")
  })

  it("fait l'aller-retour sans dérive", () => {
    const instant = "2026-11-02T22:30:00.000Z"
    const champ = toCountryLocalInput(instant, "Africa/Casablanca")

    expect(fromCountryLocalInput(champ, "Africa/Casablanca")).toBe(instant)
  })

  it("refuse une saisie qui n'est pas une date", () => {
    expect(fromCountryLocalInput("", "Africa/Lome")).toBeNull()
    expect(fromCountryLocalInput("hier", "Africa/Lome")).toBeNull()
  })
})

describe("normalizeDecimal", () => {
  afterEach(async () => {
    await i18n.changeLanguage("fr")
  })

  it("accepte la virgule et les espaces de milliers", () => {
    expect(normalizeDecimal("1 234,56")).toBe("1234.56")
    expect(normalizeDecimal("12 500,50")).toBe("12500.50")
    expect(normalizeDecimal("12.5")).toBe("12.5")
    expect(normalizeDecimal("1000")).toBe("1000")
  })

  it("lit les deux séparateurs quand ils sont tous deux présents, quelle que soit la langue", () => {
    expect(normalizeDecimal("12,500.00")).toBe("12500.00")
    expect(normalizeDecimal("1.234,56")).toBe("1234.56")
    expect(normalizeDecimal("1,234,567.89")).toBe("1234567.89")
  })

  it("tranche un séparateur seul selon la langue de l'interface", async () => {
    // En français, la virgule est décimale ; le point devant trois chiffres
    // groupe les milliers.
    expect(normalizeDecimal("12,500")).toBe("12.500")
    expect(normalizeDecimal("12.500")).toBe("12500")

    await i18n.changeLanguage("en")
    // En anglais, c'est l'inverse : « 12,500 » vaut douze mille cinq cents.
    expect(normalizeDecimal("12,500")).toBe("12500")
    expect(normalizeDecimal("12,500.00")).toBe("12500.00")
    expect(normalizeDecimal("12.500")).toBe("12.500")
    expect(normalizeDecimal("12.5")).toBe("12.5")
    expect(normalizeDecimal("1,234,567")).toBe("1234567")
  })

  it("refuse ce qui n'est pas un nombre", () => {
    expect(normalizeDecimal("")).toBeNull()
    expect(normalizeDecimal("12,3,4")).toBeNull()
    expect(normalizeDecimal("1,23.4")).toBeNull()
    expect(normalizeDecimal("abc")).toBeNull()
  })
})

describe("pluralize", () => {
  it("accorde le nom", () => {
    expect(pluralize(1, "dossier")).toBe("1 dossier")
    expect(pluralize(0, "dossier")).toBe("0 dossier")
    expect(pluralize(2, "dossier")).toBe("2 dossiers")
    expect(pluralize(3, "pays", "pays")).toBe("3 pays")
  })
})
