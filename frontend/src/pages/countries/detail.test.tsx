import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { CountryDetailPage } from "./detail"
import type { CountryDetail } from "@/lib/types"

const togo = {
  id: 2,
  name: "Togo",
  code: "TG",
  currency: "XOF",
  currency_symbol: "FCFA",
  timezone: "Africa/Lome",
  is_active: true,
  team_count: 0,
  project_count: 0,
  cost_center_count: 0,
  expense_title_count: 0,
  teams: [],
  projects: [],
  managers: [],
  cost_centers: [],
  expense_titles: [],
  marketing_categories: [],
} as unknown as CountryDetail

vi.mock("@/lib/countries", async (original) => ({
  ...(await original<typeof import("@/lib/countries")>()),
  fetchCountry: () => Promise.resolve(togo),
}))
vi.mock("@/components/countries/manage-beneficiaries", () => ({ ManageBeneficiaries: () => null }))
vi.mock("@/components/countries/manage-managers", () => ({ ManageManagers: () => null }))
vi.mock("@/components/countries/history", () => ({ CaretHistory: () => null }))

let droits = new Set<string>()
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ can: (cle: string) => droits.has(cle), me: { has_global_scope: false } }),
}))

function afficher() {
  return render(
    <MemoryRouter initialEntries={["/countries/2"]}>
      <Routes>
        <Route path="/countries/:id" element={<CountryDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

/**
 * Régression : l'onglet « Historique » s'affichait à tous, et un manager —
 * sans `history.read` par défaut — n'y lisait qu'un refus du serveur.
 */
describe("fiche d'un pays — historique", () => {
  it("tait l'onglet sans le droit de lire l'historique", async () => {
    droits = new Set()

    afficher()

    expect(await screen.findByRole("tab", { name: "Équipes" })).toBeInTheDocument()
    expect(screen.queryByRole("tab", { name: "Historique" })).toBeNull()
  })

  it("le propose avec ce droit", async () => {
    droits = new Set(["history.read"])

    afficher()

    expect(await screen.findByRole("tab", { name: "Historique" })).toBeInTheDocument()
  })
})
