import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { Pagination } from "@/components/ui/pagination"

/**
 * Régression : le compte se concaténait brut — « 1234 dossiers » —, alors que
 * tout nombre affiché passe par `Intl` ailleurs dans l'application.
 */
describe("Pagination", () => {
  it("formate le compte comme un nombre", () => {
    render(
      <Pagination page={1} count={1234} onChange={vi.fn()} noun={["dossier", "dossiers"]} />,
    )

    expect(screen.getByText(/1 234 dossiers|1 234 dossiers/)).toBeInTheDocument()
    expect(screen.queryByText(/^1234 dossiers/)).toBeNull()
  })

  it("accorde le nom au singulier", () => {
    render(<Pagination page={1} count={1} onChange={vi.fn()} noun={["dossier", "dossiers"]} />)

    expect(screen.getByText(/1 dossier$|1 dossier\b/)).toBeInTheDocument()
  })

  it("ne s'affiche pas sans résultat", () => {
    const { container } = render(
      <Pagination page={1} count={0} onChange={vi.fn()} noun={["dossier", "dossiers"]} />,
    )

    expect(container).toBeEmptyDOMElement()
  })
})
