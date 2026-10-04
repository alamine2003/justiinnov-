import { describe, expect, it } from "vitest"

import { avisBloquants, AVIS_TOLERES, type RapportNpm } from "./auditer-dependances.mts"

const BRACES = {
  name: "braces",
  title: "braces vulnerable to stack-exhaustion denial of service through deeply nested patterns",
  url: "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm",
  severity: "high",
}

/** Le rapport de la CI du 4 octobre 2026, réduit à `via`. */
const RAPPORT_CI: RapportNpm = {
  vulnerabilities: {
    "@ts-morph/common": { via: ["fast-glob"] },
    braces: { via: [BRACES] },
    "fast-glob": { via: ["micromatch"] },
    micromatch: { via: ["braces"] },
    shadcn: { via: ["fast-glob", "ts-morph"] },
    "ts-morph": { via: ["@ts-morph/common"] },
  },
}

function avec(...via: object[]): RapportNpm {
  return { vulnerabilities: { ...RAPPORT_CI.vulnerabilities, autre: { via } } }
}

describe("avisBloquants", () => {
  it("laisse passer l'avis toléré et la chaîne qui le relaie", () => {
    const { bloquants, toleresVus } = avisBloquants(RAPPORT_CI)

    expect(bloquants).toEqual([])
    expect(toleresVus).toEqual(["GHSA-vfj7-8cjw-p6xm"])
  })

  it("bloque le même rapport sans la tolérance", () => {
    const { bloquants } = avisBloquants(RAPPORT_CI, new Map())

    expect(bloquants.map((a) => a.id)).toEqual(["GHSA-vfj7-8cjw-p6xm"])
  })

  it("bloque tout autre avis high ou critical", () => {
    const { bloquants } = avisBloquants(avec(
      { name: "x", title: "X", url: "https://github.com/advisories/GHSA-aaaa", severity: "critical" },
      { name: "y", title: "Y", url: "https://github.com/advisories/GHSA-bbbb", severity: "high" },
    ))

    expect(bloquants.map((a) => a.id)).toEqual(["GHSA-aaaa", "GHSA-bbbb"])
  })

  it("ne bloque pas sous le seuil high", () => {
    const { bloquants } = avisBloquants(avec(
      { name: "z", title: "Z", url: "https://github.com/advisories/GHSA-cccc", severity: "moderate" },
    ))

    expect(bloquants).toEqual([])
  })

  it("compte une fois un avis présent sous deux paquets", () => {
    const { bloquants } = avisBloquants(
      { vulnerabilities: { braces: { via: [BRACES] }, copie: { via: [BRACES] } } },
      new Map(),
    )

    expect(bloquants).toHaveLength(1)
  })

  it("dit pourquoi chaque avis est toléré", () => {
    for (const pourquoi of AVIS_TOLERES.values()) expect(pourquoi.length).toBeGreaterThan(40)
  })
})
