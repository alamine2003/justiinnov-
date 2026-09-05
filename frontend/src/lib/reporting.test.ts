import { describe, expect, it } from "vitest"
import {
  exportExtension,
  exportFamily,
  exportFilename,
  exportParams,
  TABULAR_FORMATS,
} from "@/lib/reporting"

describe("exports — extension et famille", () => {
  it("déduit l'extension de la route", () => {
    expect(exportExtension("expenses.xlsx")).toBe("xlsx")
    expect(exportExtension("reconciliation.csv")).toBe("csv")
    expect(exportExtension("expenses.docx")).toBe("docx")
    expect(exportExtension("report.pdf")).toBe("pdf")
  })

  it("déduit la famille de la route", () => {
    expect(exportFamily("expenses.docx")).toBe("expenses")
    expect(exportFamily("reconciliation.xlsx")).toBe("reconciliation")
    expect(exportFamily("report.pdf")).toBe("report")
  })

  it("propose les trois formats tabulaires du serveur", () => {
    expect([...TABULAR_FORMATS]).toEqual(["xlsx", "csv", "docx"])
  })
})

describe("exportFilename", () => {
  it("nomme le fichier d'après la famille, l'exercice et le format", () => {
    expect(exportFilename("expenses.xlsx", { year: 2026 })).toBe("depenses-2026.xlsx")
    expect(exportFilename("reconciliation.docx", { year: 2025 })).toBe("rapprochement-2025.docx")
    expect(exportFilename("report.pdf", { year: 2026 })).toBe("rapport-2026.pdf")
  })

  it("ajoute le mois sur deux chiffres quand il borne l'export", () => {
    expect(exportFilename("expenses.csv", { year: 2026, month: 3 })).toBe("depenses-2026-03.csv")
    expect(exportFilename("report.pdf", { year: 2026, month: 12 })).toBe("rapport-2026-12.pdf")
  })

  it("ignore un mois vide", () => {
    expect(exportFilename("expenses.csv", { year: 2026, month: null })).toBe("depenses-2026.csv")
  })
})

describe("exportParams", () => {
  it("ne transmet que l'exercice par défaut", () => {
    expect(exportParams({ year: 2026 })).toEqual({ year: 2026 })
  })

  it("transmet le mois et le pays quand ils sont fixés", () => {
    expect(exportParams({ year: 2026, month: 7, country: 3 })).toEqual({
      year: 2026,
      month: 7,
      country: 3,
    })
  })

  it("omet un pays vide et un mois nul", () => {
    expect(exportParams({ year: 2026, month: null, country: "" })).toEqual({ year: 2026 })
  })
})

describe("executionWarningRate", () => {
  it("retient le seuil d'alerte le plus haut sous le plafond", async () => {
    const { EXECUTION_WARNING_RATE, executionWarningRate } = await import("@/lib/reporting")
    expect(executionWarningRate([50, 80, 100])).toBe(0.8)
    expect(executionWarningRate([90, 110])).toBe(0.9)
    expect(EXECUTION_WARNING_RATE).toBe(0.8)
  })

  it("retombe sur la constante quand la configuration n'est pas lisible", async () => {
    // Un compte pays ne lit pas la configuration : la barre garde son repli.
    const { EXECUTION_WARNING_RATE, executionWarningRate } = await import("@/lib/reporting")
    expect(executionWarningRate(undefined)).toBe(EXECUTION_WARNING_RATE)
    expect(executionWarningRate([])).toBe(EXECUTION_WARNING_RATE)
    expect(executionWarningRate([100, 120])).toBe(EXECUTION_WARNING_RATE)
  })
})
