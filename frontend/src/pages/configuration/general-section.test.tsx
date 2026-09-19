import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { GeneralSection } from "@/pages/configuration/general-section"
import type { Configuration } from "@/lib/types"

const fetchConfiguration = vi.fn()

vi.mock("@/lib/accounts", () => ({
  fetchConfiguration: (...args: unknown[]) => fetchConfiguration(...args),
  updateWorkflowConfiguration: vi.fn(),
}))

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ refreshProfile: vi.fn(async () => {}), can: () => false }),
}))

/** Réglages effectifs tels que le serveur les rend, une seule devise. */
function configuration(overrides: Partial<Configuration> = {}): Configuration {
  return {
    alertes: { seuils: [80, 90, 100], facteur_depense_inhabituelle: 5 },
    justificatifs: {
      taille_max_mo: 20,
      formats_acceptes: [".pdf", ".jpg"],
      stockage: "Disque local",
    },
    budget: { devise_de_consolidation: "XOF" },
    notifications: { email_configure: true, expediteur: "controle-budgetaire@justi-innov.local" },
    systeme: { fuseau: "UTC", mode_debug: false, version_api: "dev" },
    workflow: {
      require_review_step: false,
      unjustified_alert_days: 0,
      alert_thresholds: [80, 90, 100],
      unusual_expense_factor: "5.00",
      default_overrun_policy: "block",
      default_overrun_policy_display: "Bloquer",
      warn_without_proof_submission: true,
      updated_at: "2026-01-01T00:00:00Z",
    },
    supervision: false,
    ...overrides,
  }
}

describe("GeneralSection — version de l'API", () => {
  it("affiche la version rendue par le serveur, dans le bloc Application", async () => {
    fetchConfiguration.mockResolvedValue(configuration({ systeme: { fuseau: "UTC", mode_debug: false, version_api: "sha-abc123def456" } }))

    render(<GeneralSection />)

    expect(await screen.findByText("sha-abc123def456")).toBeInTheDocument()
    // La ligne porte le libellé du dictionnaire, pas une chaîne en dur.
    expect(screen.getByText("Version de l'API")).toBeInTheDocument()
  })

  it("affiche « dev » quand le déploiement ne pose pas APP_VERSION", async () => {
    fetchConfiguration.mockResolvedValue(configuration())

    render(<GeneralSection />)

    expect(await screen.findByText("dev")).toBeInTheDocument()
  })
})
