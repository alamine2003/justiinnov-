import { describe, expect, it } from "vitest"

import { formatAmount, formatDate, formatRate } from "./utils"

/**
 * `Intl` sépare les milliers par une espace fine insécable, dont le point de
 * code a varié selon les versions de Node. Comparer sur une espace ordinaire
 * rend le test indépendant de cette variation.
 */
const normalise = (value: string) => value.replace(/[\s\u202f\u00a0]/g, " ")

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
