import { render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { DossiersPage } from "@/pages/dossiers/list"

const fetchDossiers = vi.fn()
const fetchDossierCounts = vi.fn()

vi.mock("@/lib/expenses", () => ({
  fetchDossiers: (...args: unknown[]) => fetchDossiers(...args),
  fetchDossierCounts: (...args: unknown[]) => fetchDossierCounts(...args),
  createDossier: vi.fn(),
}))
vi.mock("@/lib/countries", () => ({
  fetchCountries: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
  fetchCountry: vi.fn(),
}))
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ me: { has_global_scope: true, teams: [] }, can: () => false }),
}))

function afficher(url = "/dossiers") {
  fetchDossiers.mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
  fetchDossierCounts.mockResolvedValue({
    total: 42,
    by_status: { draft: 8, submitted: 6, in_review: 11, justified: 12, unjustified: 3, closed: 2 },
  })
  return render(
    <MemoryRouter initialEntries={[url]}>
      <DossiersPage />
    </MemoryRouter>,
  )
}

describe("DossiersPage — pastilles de statut", () => {
  it("compte les dossiers de chaque statut, tels que le serveur les donne", async () => {
    afficher()

    const groupe = screen.getByRole("group", { name: "Filtrer par statut" })
    await waitFor(() =>
      expect(within(groupe).getByRole("button", { name: "Tous · 42" })).toBeInTheDocument(),
    )
    expect(within(groupe).getByRole("button", { name: "Brouillon · 8" })).toBeInTheDocument()
    expect(within(groupe).getByRole("button", { name: "Non justifié · 3" })).toBeInTheDocument()
    expect(within(groupe).getByRole("button", { name: "Tous · 42" })).toHaveAttribute("aria-pressed", "true")
  })

  it("presse la pastille du statut de l'URL", async () => {
    afficher("/dossiers?status=in_review")

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "En contrôle · 11" })).toHaveAttribute("aria-pressed", "true"),
    )
    expect(screen.getByRole("button", { name: "Tous · 42" })).toHaveAttribute("aria-pressed", "false")
    // La liste est filtrée ; les comptes, eux, ne le sont pas.
    expect(fetchDossiers).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "in_review" }),
      expect.anything(),
    )
    expect(fetchDossierCounts).toHaveBeenLastCalledWith(undefined, expect.anything())
  })
})
