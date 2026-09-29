import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DossiersPage } from "./list"
import { invalidateReferentiel } from "@/lib/referentiel"

const fetchCountries = vi.fn()
const createDossier = vi.fn()
const fetchDossiers = vi.fn()
const fetchDossiersParPays = vi.fn()
vi.mock("@/lib/expenses", () => ({
  fetchDossiers: (...args: unknown[]) => fetchDossiers(...args),
  fetchDossiersParPays: (...args: unknown[]) => fetchDossiersParPays(...args),
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

const PAR_PAYS = {
  total: 7,
  pays: [
    { id: ivoire.id, name: ivoire.name, code: "CI", country_ref: "CI", count: 5 },
    { id: togo.id, name: togo.name, code: "TG", country_ref: "TG", count: 2 },
  ],
}

beforeEach(() => {
  droits = null
  fetchDossiers.mockReset()
  fetchDossiers.mockResolvedValue(PAGE_VIDE)
  fetchDossiersParPays.mockReset()
  fetchDossiersParPays.mockResolvedValue(PAR_PAYS)
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
 * les pays, lit la liste pays par pays, en onglets. Chaque onglet porte le
 * nombre de dossiers compté par le serveur, et le pays choisi part au
 * serveur.
 */
describe("DossiersPage — onglets par pays", () => {
  beforeEach(() => {
    invalidateReferentiel("countries")
    fetchCountries.mockResolvedValue({ count: 2, next: null, previous: null, results: [togo, ivoire] })
  })

  it("montre un onglet par pays, avec le compte du serveur", async () => {
    render(
      <MemoryRouter>
        <DossiersPage />
      </MemoryRouter>,
    )
    const onglets = await screen.findByRole("tablist", { name: "Filtrer par pays" })
    await waitFor(() => expect(screen.getByRole("tab", { name: /Togo/ })).toBeInTheDocument())

    expect(screen.getByRole("tab", { name: "Tous les pays 7" })).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("tab", { name: "Côte d'Ivoire 5" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Togo 2" })).toBeInTheDocument()
    expect(onglets).toBeInTheDocument()
  })

  it("envoie le pays de l'onglet choisi au serveur", async () => {
    render(
      <MemoryRouter>
        <DossiersPage />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole("tab", { name: /Côte d'Ivoire/ }))

    await waitFor(() =>
      expect(fetchDossiers).toHaveBeenLastCalledWith(
        expect.objectContaining({ country: ivoire.id, page: 1 }),
        expect.anything(),
      ),
    )
    expect(screen.getByRole("tab", { name: /Côte d'Ivoire/ })).toHaveAttribute("aria-selected", "true")
  })

  it("compte avec les filtres de la liste, sans le pays", async () => {
    render(
      <MemoryRouter initialEntries={[`/dossiers?country=${togo.id}&status=submitted`]}>
        <DossiersPage />
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(fetchDossiersParPays).toHaveBeenCalledWith({ status: "submitted" }, expect.anything()),
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
    expect(await screen.findByRole("tab", { name: /Togo/ })).toHaveAttribute("aria-selected", "true")
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
