import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DossiersPage } from "./list"
import { invalidateReferentiel } from "@/lib/referentiel"

const fetchCountries = vi.fn()
const createDossier = vi.fn()
vi.mock("@/lib/expenses", () => ({
  fetchDossiers: () => Promise.resolve({ count: 0, next: null, previous: null, results: [] }),
  createDossier: (...args: unknown[]) => createDossier(...args),
}))
vi.mock("@/lib/countries", () => ({
  fetchCountries: () => fetchCountries(),
  fetchCountry: () => Promise.resolve({ teams: [], managers: [] }),
}))
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: { has_global_scope: true, countries: [], teams: [] },
    can: () => true,
  }),
}))
vi.mock("@/components/reporting/export-menu", () => ({ ExportMenu: () => null }))

const togo = { id: 1, name: "Togo", code: "TG", country_ref: "TG", is_active: true }

/**
 * Régression : le formulaire pré-remplissait le pays *au montage* avec le
 * premier de la liste. Ouvert avant que la liste n'arrive, il gardait un pays
 * vide qu'aucune option ne représentait : le navigateur affichait le premier
 * pays comme choisi, et la soumission répondait « Choisissez un pays. » à
 * quelqu'un qui croyait l'avoir fait.
 */
describe("DossiersPage — formulaire ouvert avant les pays", () => {
  beforeEach(() => {
    invalidateReferentiel("countries")
    createDossier.mockReset()
  })

  it("montre un choix vide, explicite, quand la liste arrive après l'ouverture", async () => {
    let livrer: (page: unknown) => void = () => {}
    fetchCountries.mockReturnValue(new Promise((resolve) => (livrer = resolve)))
    render(
      <MemoryRouter>
        <DossiersPage />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole("button", { name: "Nouveau dossier" }))
    const pays = (await screen.findByLabelText("Pays")) as HTMLSelectElement
    expect(pays.selectedOptions[0]?.textContent).toBe("Aucun pays disponible")

    livrer({ count: 1, next: null, previous: null, results: [togo] })

    await waitFor(() => expect(screen.getByRole("option", { name: /Togo/ })).toBeInTheDocument())
    expect(pays.value).toBe("")
    expect(pays.selectedOptions[0]?.textContent).toBe("Choisissez un pays…")

    fireEvent.change(screen.getByLabelText("N°ORDRE"), { target: { value: "N-2026-001" } })
    fireEvent.change(screen.getByLabelText("Libellé"), { target: { value: "Mission" } })
    fireEvent.click(screen.getByRole("button", { name: "Créer" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Choisissez un pays.")
    expect(createDossier).not.toHaveBeenCalled()
  })
})
