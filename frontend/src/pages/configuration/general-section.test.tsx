import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { GeneralSection } from "./general-section"

const workflow = {
  require_review_step: true,
  warn_without_proof_submission: true,
  unjustified_alert_days: 30,
  unusual_expense_factor: "5",
  alert_thresholds: [80, 90, 100],
  default_overrun_policy: "block",
  suppressions_ouvertes: false,
}

const configuration = {
  systeme: { fuseau: "UTC", mode_debug: false },
  alertes: { seuils: [80, 90, 100], facteur_depense_inhabituelle: "5" },
  justificatifs: { stockage: "local", taille_max_mo: 20, formats_acceptes: [".pdf"] },
  budget: { devise_de_consolidation: "XOF" },
  notifications: { email_actif: false, email_configure: false, expediteur: "x@innovpharma.net" },
  workflow,
}

const updateWorkflowConfiguration = vi.fn()
vi.mock("@/lib/accounts", () => ({
  fetchConfiguration: () => Promise.resolve(configuration),
  updateWorkflowConfiguration: (...args: unknown[]) => updateWorkflowConfiguration(...args),
}))
vi.mock("./rates-section", () => ({ RatesSection: () => null }))

const refreshProfile = vi.fn(async () => {})
/** Les droits du compte ; la corbeille n'est qu'au super administrateur. */
let corbeille = true
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    refreshProfile,
    can: (cle: string) => cle !== "corbeille.supprimer" || corbeille,
    me: { role: "admin" },
  }),
}))

function monter() {
  return render(
    <MemoryRouter>
      <GeneralSection />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  corbeille = true
  updateWorkflowConfiguration.mockReset()
  refreshProfile.mockClear()
})

/**
 * Régression : après un changement de seuils, le profil n'était pas relu.
 * Les rails des enveloppes lisent `me.alert_thresholds` : leurs graduations
 * restaient les anciennes, la couleur suivait déjà les nouvelles.
 */
describe("GeneralSection — politique", () => {
  it("relit le profil après l'enregistrement", async () => {
    updateWorkflowConfiguration.mockResolvedValue({ ...workflow, alert_thresholds: [70, 90, 100] })

    monter()

    fireEvent.click(await screen.findByRole("button", { name: "Enregistrer la politique" }))

    await waitFor(() => expect(updateWorkflowConfiguration).toHaveBeenCalled())
    await waitFor(() => expect(refreshProfile).toHaveBeenCalled())
    expect(await screen.findByText("Politique enregistrée")).toBeInTheDocument()
  })
})

/** La corbeille du super administrateur (décision 120). */
describe("GeneralSection — corbeille", () => {
  it("le super administrateur l'ouvre d'un geste, et le profil est relu", async () => {
    updateWorkflowConfiguration.mockResolvedValue({ ...workflow, suppressions_ouvertes: true })

    monter()
    fireEvent.click(await screen.findByRole("switch", { name: "Suppressions ouvertes" }))

    await waitFor(() =>
      expect(updateWorkflowConfiguration).toHaveBeenCalledWith({ suppressions_ouvertes: true }),
    )
    await waitFor(() => expect(refreshProfile).toHaveBeenCalled())
    expect(await screen.findByText(/La corbeille est ouverte\./)).toBeInTheDocument()
  })

  it("la RH la voit sans pouvoir la régler", async () => {
    corbeille = false

    monter()

    // Le Switch de Base UI se dit désactivé par `aria-disabled`.
    expect(await screen.findByRole("switch", { name: "Suppressions ouvertes" })).toHaveAttribute(
      "aria-disabled",
      "true",
    )
    expect(
      screen.getByText(/Seul le super administrateur ouvre ou ferme la corbeille\./),
    ).toBeInTheDocument()
  })
})
