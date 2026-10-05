import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { GeneralSection } from "./general-section"

const workflow = {
  require_review_step: true,
  warn_without_proof_submission: true,
  unjustified_alert_days: 30,
  unusual_expense_factor: "5",
  alert_thresholds: [80, 90, 100],
  default_overrun_policy: "block",
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
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ refreshProfile, can: () => true, me: { role: "admin" } }),
}))

/**
 * Régression : après un changement de seuils, le profil n'était pas relu.
 * Les rails des enveloppes lisent `me.alert_thresholds` : leurs graduations
 * restaient les anciennes, la couleur suivait déjà les nouvelles.
 */
describe("GeneralSection — politique", () => {
  it("relit le profil après l'enregistrement", async () => {
    updateWorkflowConfiguration.mockResolvedValue({ ...workflow, alert_thresholds: [70, 90, 100] })

    render(<GeneralSection />)

    fireEvent.click(await screen.findByRole("button", { name: "Enregistrer la politique" }))

    await waitFor(() => expect(updateWorkflowConfiguration).toHaveBeenCalled())
    await waitFor(() => expect(refreshProfile).toHaveBeenCalled())
    expect(await screen.findByText("Politique enregistrée")).toBeInTheDocument()
  })
})
