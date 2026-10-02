import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { DiffList } from "./history"

/**
 * L'avant / après du journal se lit sans connaître le modèle : les champs
 * sous leur nom, les statuts sous leur libellé, les montants formatés, et
 * seulement ce qui a changé (décisions 110 et 111).
 */
describe("DiffList", () => {
  it("traduit champs et statuts, formate les montants, tait ce qui n'a pas changé", () => {
    render(
      <DiffList
        diff={{
          status: ["submitted", "justified"],
          justified_amount: ["0.00", "100000.00"],
          note: ["", ""],
        }}
      />,
    )

    expect(screen.getByText("Soumis")).toBeInTheDocument()
    expect(screen.getByText("Justifié")).toBeInTheDocument()
    expect(screen.getByText(/100 000/)).toBeInTheDocument()
    expect(screen.queryByText("submitted")).toBeNull()
    expect(screen.queryByText(/justified_amount/)).toBeNull()
    expect(screen.queryByText(/^Motif/)).toBeNull()
  })

  it("ne formate pas l'enveloppe imputée en montant : c'est un identifiant", () => {
    render(<DiffList diff={{ budget: [1200, null] }} />)

    expect(screen.getByText("1200")).toBeInTheDocument()
    expect(screen.queryByText(/1 200/)).toBeNull()
  })

  it("ne rend rien quand rien n'a changé", () => {
    const { container } = render(<DiffList diff={{ note: ["", ""] }} />)

    expect(container).toBeEmptyDOMElement()
  })
})
