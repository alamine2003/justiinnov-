import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DossiersPage } from "./list"
import { invalidateReferentiel } from "@/lib/referentiel"

const fetchCountries = vi.fn()
const createDossier = vi.fn()
const fetchDossiers = vi.fn()
vi.mock("@/lib/expenses", () => ({
  fetchDossiers: (...args: unknown[]) => fetchDossiers(...args),
  createDossier: (...args: unknown[]) => createDossier(...args),
}))
vi.mock("@/lib/countries", () => ({
  fetchCountries: () => fetchCountries(),
  fetchCountry: () => Promise.resolve({ teams: [], managers: [] }),
}))
let droits: Record<string, boolean> | null = null
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: { has_global_scope: true, countries: [], teams: [] },
    can: (cle: string) => (droits === null ? true : (droits[cle] ?? false)),
  }),
}))
vi.mock("@/components/reporting/export-menu", () => ({ ExportMenu: () => null }))

const togo = { id: 1, name: "Togo", code: "TG", country_ref: "TG", is_active: true }
const ivoire = { id: 2, name: "Côte d'Ivoire", code: "CI", country_ref: "CI", is_active: true }
const PAGE_VIDE = { count: 0, next: null, previous: null, results: [] }

beforeEach(() => {
  droits = null
  fetchDossiers.mockReset()
  fetchDossiers.mockResolvedValue(PAGE_VIDE)
})

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

/**
 * Un dossier appartient à un pays (décision 89) : le siège, qui voit tous
 * les pays, filtre la liste par pays, et le filtre part au serveur.
 */
describe("DossiersPage — filtre par pays", () => {
  beforeEach(() => {
    invalidateReferentiel("countries")
    fetchCountries.mockResolvedValue({ count: 2, next: null, previous: null, results: [togo, ivoire] })
  })

  it("envoie le pays choisi au serveur", async () => {
    render(
      <MemoryRouter>
        <DossiersPage />
      </MemoryRouter>,
    )
    const filtre = await screen.findByLabelText("Filtrer par pays")
    await waitFor(() => expect(screen.getAllByRole("option", { name: /Côte d'Ivoire/ }).length).toBeGreaterThan(0))

    fireEvent.change(filtre, { target: { value: String(ivoire.id) } })

    await waitFor(() =>
      expect(fetchDossiers).toHaveBeenLastCalledWith(
        expect.objectContaining({ country: ivoire.id, page: 1 }),
        expect.anything(),
      ),
    )
  })

  it("reprend le pays de l'URL", async () => {
    render(
      <MemoryRouter initialEntries={[`/dossiers?country=${togo.id}`]}>
        <DossiersPage />
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(fetchDossiers).toHaveBeenCalledWith(
        expect.objectContaining({ country: togo.id }),
        expect.anything(),
      ),
    )
  })
})

describe("DossiersPage — import", () => {
  beforeEach(() => {
    invalidateReferentiel("countries")
    fetchCountries.mockResolvedValue({ count: 1, next: null, previous: null, results: [togo] })
  })

  it("propose l'import à qui peut importer, vers sa page", async () => {
    droits = { "data.import": true, "expenses.create": true }
    render(
      <MemoryRouter>
        <DossiersPage />
      </MemoryRouter>,
    )

    // Le bouton de base-ui rendu en lien garde le rôle « button », comme
    // l'entrée « Activer la 2FA » du menu.
    expect(await screen.findByRole("button", { name: "Importer" })).toHaveAttribute(
      "href",
      "/dossiers/import",
    )
  })

  it("ne le propose pas au siège, qui ne déclare pas", async () => {
    droits = { "data.export": true }
    render(
      <MemoryRouter>
        <DossiersPage />
      </MemoryRouter>,
    )

    await screen.findByLabelText("Filtrer par pays")
    expect(screen.queryByRole("button", { name: "Importer" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Nouveau dossier" })).toBeNull()
  })
})
