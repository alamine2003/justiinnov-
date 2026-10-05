import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { BudgetForm } from "./budget-form"
import type { CountrySummary } from "@/lib/types"

const pays = [
  { id: 1, name: "Côte d'Ivoire", country_ref: "CI-01", currency: "XOF" },
  { id: 2, name: "Togo", country_ref: "TG-01", currency: "XOF" },
] as unknown as CountrySummary[]

function ouvrir(props: Partial<Parameters<typeof BudgetForm>[0]> = {}) {
  return render(
    <BudgetForm
      open
      onOpenChange={vi.fn()}
      onSave={vi.fn()}
      countries={pays}
      projects={[]}
      teams={[]}
      editing={null}
      {...props}
    />,
  )
}

/**
 * Régression : « Découper l'enveloppe » du Togo ouvrait le formulaire sur
 * le premier pays de la liste, la Côte d'Ivoire, et ses équipes.
 */
describe("BudgetForm — pays et portée proposés", () => {
  it("découpe l'enveloppe du pays ouvert, par projet", () => {
    ouvrir({ defaultCountry: 2, defaultScope: "project" })

    expect(screen.getByLabelText("Pays")).toHaveValue("2")
    expect(screen.getByLabelText(/Portée/)).toHaveValue("project")
  })

  it("ne choisit aucun pays à la place de la personne", () => {
    ouvrir()

    expect(screen.getByLabelText("Pays")).toHaveValue("")
  })
})
