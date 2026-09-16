import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { act } from "@testing-library/react"
import { MontantNormalise } from "@/components/ui/montant-normalise"
import i18n from "@/i18n"

afterEach(async () => {
  await act(() => i18n.changeLanguage("fr"))
})

/**
 * `normalizeDecimal` tranche l'ambiguïté des séparateurs d'après la langue,
 * et le faisait en silence : en français, « 150,000 » vaut cent cinquante.
 * Un manager habitué aux montants anglo-saxons enregistrait 150 FCFA au lieu
 * de 150 000, sans rien voir avant le rapprochement de la pièce.
 */
describe("MontantNormalise", () => {
  it("montre ce qui sera enregistré quand la saisie est ambiguë", () => {
    render(<MontantNormalise value="150,000" currency="FCFA" />)

    expect(screen.getByText("Sera enregistré : 150 FCFA")).toBeInTheDocument()
  })

  it("lit le point comme des milliers en français", () => {
    render(<MontantNormalise value="150.000" currency="FCFA" />)

    expect(screen.getByText("Sera enregistré : 150 000 FCFA")).toBeInTheDocument()
  })

  it("se tait sur une saisie sans séparateur, qui ne se lit que d'une façon", () => {
    const { container } = render(<MontantNormalise value="150000" currency="FCFA" />)

    expect(container).toBeEmptyDOMElement()
  })

  it("se tait sur une saisie vide ou illisible", () => {
    expect(render(<MontantNormalise value="" />).container).toBeEmptyDOMElement()
    expect(render(<MontantNormalise value="1,2,3" />).container).toBeEmptyDOMElement()
  })

  it("suit la langue de l'interface", async () => {
    await act(() => i18n.changeLanguage("en"))
    render(<MontantNormalise value="150,000" currency="FCFA" />)

    // En anglais la virgule groupe les milliers : la même saisie vaut mille
    // fois plus, et c'est précisément ce que l'écho doit rendre visible.
    expect(screen.getByText("Will be recorded as: 150,000 FCFA")).toBeInTheDocument()
  })
})
