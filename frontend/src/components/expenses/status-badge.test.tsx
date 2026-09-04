/**
 * Régression : les couleurs de statut étaient des teintes Tailwind brutes,
 * identiques dans les deux thèmes. Sur fond sombre, le texte blanc des badges
 * passait sous le seuil de contraste.
 */
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { StatusBadge } from "@/components/expenses/status-badge"
import {
  ACTION_STYLE,
  ALERT_LEVEL_STYLE,
  PROJECT_STYLE,
  PROOF_STYLE,
  REALLOCATION_STYLE,
  WORKFLOW_STYLE,
} from "@/lib/status-styles"
import type { ProofStatus, WorkflowStatus } from "@/lib/types"

/** Teintes Tailwind brutes et blanc en dur : interdits par DESIGN.md. */
const TEINTE_BRUTE = /\b(?:bg|text|border)-(?:emerald|red|green|amber|blue|slate|zinc|gray|yellow|orange)-\d{3}\b|\btext-white\b/

function fichiersSource(dossier: string): string[] {
  return readdirSync(dossier).flatMap((nom) => {
    const chemin = join(dossier, nom)
    if (statSync(chemin).isDirectory()) return fichiersSource(chemin)
    return /\.(tsx?|css)$/.test(nom) && !nom.endsWith(".test.tsx") && !nom.endsWith(".test.ts")
      ? [chemin]
      : []
  })
}

describe("StatusBadge", () => {
  it("chaque statut du workflow a une couleur", () => {
    const statuses: WorkflowStatus[] = [
      "draft", "submitted", "in_review", "justified", "unjustified", "closed",
    ]

    expect(Object.keys(WORKFLOW_STYLE)).toEqual(expect.arrayContaining(statuses))
    expect(Object.keys(WORKFLOW_STYLE)).toHaveLength(statuses.length)
  })

  it("chaque statut de justificatif a une couleur", () => {
    const statuses: ProofStatus[] = [
      "received", "incomplete", "to_review", "validated", "rejected", "archived",
    ]

    expect(Object.keys(PROOF_STYLE)).toEqual(expect.arrayContaining(statuses))
    expect(Object.keys(PROOF_STYLE)).toHaveLength(statuses.length)
  })

  it("aucune teinte Tailwind brute ne subsiste dans les tables de style", () => {
    const tables = [
      WORKFLOW_STYLE, PROOF_STYLE, PROJECT_STYLE,
      REALLOCATION_STYLE, ALERT_LEVEL_STYLE, ACTION_STYLE,
    ]

    for (const table of tables) {
      expect(Object.values(table).some((value) => TEINTE_BRUTE.test(value))).toBe(false)
    }
  })

  it("aucune couleur en dur ne subsiste dans src/", () => {
    // Le texte d'un badge « rejeté » était blanc en dur, illisible sur le
    // rouge atténué du thème sombre ; une icône « approuver » était en
    // `text-emerald-600`, hors palette. Un grep échoue désormais au test.
    const fautifs = fichiersSource(join(import.meta.dirname, "../../")).filter((chemin) =>
      TEINTE_BRUTE.test(readFileSync(chemin, "utf8")),
    )

    expect(fautifs).toEqual([])
  })

  it("le libellé français est affiché", () => {
    render(<StatusBadge status="justified" />)

    expect(screen.getByText("Justifié")).toBeInTheDocument()
  })

  it("préfère le libellé du serveur quand il est fourni", () => {
    render(<StatusBadge status="justified" label="Justifiée" />)

    expect(screen.getByText("Justifiée")).toBeInTheDocument()
  })
})
