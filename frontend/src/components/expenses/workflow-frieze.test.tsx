/**
 * La frise dit où en est un dossier. Elle ne doit jamais dire qu'une étape
 * est franchie alors qu'elle ne l'est pas — et le constat de non-justification
 * n'est pas une étape de plus : il prend la place de « justifié ».
 */
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { FriseDuCircuit } from "@/components/expenses/workflow-frieze"
import { CIRCUIT } from "@/lib/labels"

describe("FriseDuCircuit", () => {
  it("montre le circuit entier, quel que soit l'état", () => {
    render(<FriseDuCircuit status="draft" />)

    expect(screen.getAllByRole("listitem")).toHaveLength(CIRCUIT.length)
  })

  it("marque l'étape courante", () => {
    render(<FriseDuCircuit status="in_review" />)

    const etapes = screen.getAllByRole("listitem")
    expect(etapes[2]).toHaveAttribute("aria-current", "step")
    expect(etapes[0]).not.toHaveAttribute("aria-current")
    expect(etapes[3]).not.toHaveAttribute("aria-current")
  })

  it("place le constat de non-justification à la place de « justifié »", () => {
    render(<FriseDuCircuit status="unjustified" />)

    const etapes = screen.getAllByRole("listitem")
    expect(etapes[3]).toHaveAttribute("aria-current", "step")
    expect(screen.getByText("Non justifié")).toBeInTheDocument()
    expect(screen.queryByText("Justifié")).toBeNull()
  })

  it("montre le circuit achevé une fois le dossier clôturé", () => {
    render(<FriseDuCircuit status="closed" />)

    const etapes = screen.getAllByRole("listitem")
    expect(etapes[CIRCUIT.length - 1]).toHaveAttribute("aria-current", "step")
    expect(screen.getByText("Justifié")).toBeInTheDocument()
  })
})
