import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { GeneralSection } from "./general-section"
import { BRAND } from "@/lib/brand"

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
/** La version du serveur que donne `/api/me/` (décision 126). */
let versionDuServeur: string | null = null
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    refreshProfile,
    can: (cle: string) => cle !== "corbeille.supprimer" || corbeille,
    me: { role: "admin", api_version: versionDuServeur },
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
  versionDuServeur = null
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

  it("la RH n'en voit rien (2.3.2)", async () => {
    corbeille = false

    monter()

    // Le reste de la page se charge : la section de la corbeille, elle, n'y est pas.
    expect(await screen.findByRole("button", { name: "Enregistrer la politique" })).toBeInTheDocument()
    expect(screen.queryByRole("switch", { name: "Suppressions ouvertes" })).toBeNull()
    expect(screen.queryByText("Corbeille")).toBeNull()
    expect(screen.queryByRole("link", { name: "Voir la corbeille" })).toBeNull()
  })
})

/** Décision 126 : la version du serveur à côté de celle de l'interface. */
describe("GeneralSection — versions", () => {
  it("montre la version du serveur quand elle est donnée", async () => {
    versionDuServeur = BRAND.version
    monter()

    expect(await screen.findByText("Version du serveur")).toBeInTheDocument()
    expect(screen.getByText("Version de l'interface")).toBeInTheDocument()
    expect(screen.queryByText(/différente de l'interface/)).toBeNull()
  })

  it("signale un serveur d'une autre livraison", async () => {
    versionDuServeur = "0.0.1"
    monter()

    expect(await screen.findByText("0.0.1 — différente de l'interface")).toBeInTheDocument()
  })

  it("se tait sans version du serveur", async () => {
    monter()

    expect(await screen.findByText("Version de l'interface")).toBeInTheDocument()
    expect(screen.queryByText("Version du serveur")).toBeNull()
  })
})
