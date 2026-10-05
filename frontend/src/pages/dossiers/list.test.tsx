import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DossiersPage } from "./list"

const fetchDossiers = vi.fn()
const fetchDossiersParPays = vi.fn()
vi.mock("@/lib/expenses", () => ({
  fetchDossiers: (...args: unknown[]) => fetchDossiers(...args),
  fetchDossiersParPays: (...args: unknown[]) => fetchDossiersParPays(...args),
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
 * Un dossier appartient à un pays (décision 89) : le siège, qui voit tous
 * les pays, lit la liste pays par pays, en onglets. Chaque onglet porte le
 * nombre de dossiers compté par le serveur, et le pays choisi part au
 * serveur.
 */
describe("DossiersPage — onglets par pays", () => {
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

  it("n'ouvre plus de dossier ici : un dossier s'ouvre dans son projet", async () => {
    droits = { "data.import": true, "expenses.create": true }
    render(
      <MemoryRouter>
        <DossiersPage />
      </MemoryRouter>,
    )

    await screen.findByRole("button", { name: "Importer" })
    expect(screen.queryByRole("button", { name: "Nouveau dossier" })).toBeNull()
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

/**
 * Régression : un filtre sans résultat invitait à créer un projet, comme si
 * le pays n'avait aucun dossier.
 */
describe("DossiersPage — état vide", () => {
  it("dit que les filtres n'ont rien trouvé, sans inviter à créer", async () => {
    droits = { "expenses.create": true }

    render(
      <MemoryRouter initialEntries={["/dossiers?status=closed"]}>
        <DossiersPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText("Aucun dossier ne correspond à ces filtres.")).toBeInTheDocument()
    expect(screen.queryByText(/Créez un projet/)).toBeNull()
  })
})

/**
 * Décision 117 : la tuile « Dossiers ouverts » ouvre la liste sur les
 * dossiers ouverts de son exercice et de son pays — le même chiffre.
 */
describe("DossiersPage — venue de la tuile « Dossiers ouverts »", () => {
  it("passe ouverts, exercice et pays au serveur, et laisse lever l'exercice", async () => {
    render(
      <MemoryRouter initialEntries={["/dossiers?ouverts=1&exercice=2026&country=1"]}>
        <DossiersPage />
      </MemoryRouter>,
    )

    await waitFor(() => expect(fetchDossiers).toHaveBeenCalled())
    expect(fetchDossiers.mock.calls.at(-1)?.[0]).toMatchObject({ ouverts: true, exercice: 2026, country: 1 })
    expect(fetchDossiers.mock.calls.at(-1)?.[0]).not.toHaveProperty("status")
    expect(fetchDossiersParPays.mock.calls.at(-1)?.[0]).toMatchObject({ ouverts: true, exercice: 2026 })
    expect(screen.getByText("Exercice 2026 seulement")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /^Ouverts/ })).toHaveAttribute("aria-pressed", "true")

    fireEvent.click(screen.getByRole("button", { name: "Voir toutes les années" }))

    await waitFor(() => expect(fetchDossiers.mock.calls.at(-1)?.[0]).not.toHaveProperty("exercice"))
    expect(fetchDossiers.mock.calls.at(-1)?.[0]).toMatchObject({ ouverts: true })
    expect(screen.queryByText("Exercice 2026 seulement")).toBeNull()
  })
})
