import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ProjetsPage } from "./list"
import { invalidateReferentiel } from "@/lib/referentiel"

const fetchCountries = vi.fn()
const fetchProjects = vi.fn()
const fetchProjectsParPays = vi.fn()
const createProject = vi.fn()
vi.mock("@/lib/countries", () => ({
  fetchCountries: () => fetchCountries(),
  fetchProjects: (...args: unknown[]) => fetchProjects(...args),
  fetchProjectsParPays: (...args: unknown[]) => fetchProjectsParPays(...args),
  createProject: (...args: unknown[]) => createProject(...args),
}))
let droits: Record<string, boolean> = {}
let global = true
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: { has_global_scope: global, countries: [], teams: [] },
    can: (cle: string) => droits[cle] ?? false,
  }),
}))

const togo = { id: 1, name: "Togo", code: "TG", country_ref: "TG", is_active: true }
const ivoire = { id: 2, name: "Côte d'Ivoire", code: "CI", country_ref: "CI", is_active: true }
const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })

const congres = {
  id: 7, country: togo.id, country_name: "Togo", name: "Congrès de Lomé",
  status: "active", status_display: "En cours", kind: "congres", kind_display: "Congrès",
  reference: "TG-P-2026-001", is_historical: false, a_typer: false, dossier_count: 3,
  accepte_des_dossiers: true, is_active: true,
}
const ancien = {
  ...congres, id: 8, name: "Projet d'avant", kind: "", kind_display: "",
  reference: "TG-P-2025-001", a_typer: true, accepte_des_dossiers: false,
}

function afficher(url = "/projets") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/projets" element={<ProjetsPage />} />
        <Route path="/projets/:id" element={<p>Fiche du projet</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  droits = {}
  global = true
  invalidateReferentiel()
  fetchProjects.mockReset()
  fetchProjects.mockResolvedValue(page([congres, ancien]))
  fetchProjectsParPays.mockReset()
  fetchProjectsParPays.mockResolvedValue({
    total: 2,
    pays: [{ id: togo.id, name: "Togo", code: "TG", country_ref: "TG", count: 2 }],
  })
  fetchCountries.mockReset()
  fetchCountries.mockResolvedValue(page([togo, ivoire]))
  createProject.mockReset()
})

describe("ProjetsPage — la liste", () => {
  it("mène à chaque projet et signale celui qui reste à typer", async () => {
    afficher()

    expect(await screen.findByRole("link", { name: "Congrès de Lomé" })).toHaveAttribute("href", "/projets/7")
    const ligne = screen.getByRole("row", { name: /Congrès de Lomé/ })
    expect(within(ligne).getByText("TG-P-2026-001")).toBeInTheDocument()
    expect(within(ligne).getByText("Congrès")).toBeInTheDocument()
    expect(within(screen.getByRole("row", { name: /Projet d'avant/ })).getByText("À typer")).toBeInTheDocument()
  })

  it("filtre par type de projet et par pays, côté serveur", async () => {
    afficher(`/projets?country=${togo.id}`)
    fireEvent.click(await screen.findByRole("button", { name: /Voyage/ }))

    await waitFor(() =>
      expect(fetchProjects).toHaveBeenLastCalledWith(
        expect.objectContaining({ kind: "voyage", country: togo.id, page: 1 }),
        expect.anything(),
      ),
    )
    // Les onglets comptent avec les filtres de la liste, sans le pays.
    await waitFor(() =>
      expect(fetchProjectsParPays).toHaveBeenLastCalledWith({ kind: "voyage" }, expect.anything()),
    )
  })

  it("n'a pas d'onglets pour un manager d'un seul pays", async () => {
    global = false
    afficher()

    await screen.findByRole("link", { name: "Congrès de Lomé" })
    expect(screen.queryByRole("tablist")).toBeNull()
    expect(fetchProjectsParPays).not.toHaveBeenCalled()
  })

  it("ne propose « Nouveau projet » qu'avec projets.create", async () => {
    afficher()
    await screen.findByRole("link", { name: "Congrès de Lomé" })
    expect(screen.queryByRole("button", { name: "Nouveau projet" })).toBeNull()
  })
})

describe("ProjetsPage — nouveau projet", () => {
  beforeEach(() => {
    droits = { "projets.create": true }
  })

  /**
   * Régression reprise de l'ancien formulaire de dossier : ouvert avant
   * que la liste des pays n'arrive, il ne doit pas montrer un pays comme
   * choisi alors que rien ne l'est.
   */
  it("montre un choix vide, explicite, quand la liste arrive après l'ouverture", async () => {
    let livrer: (valeur: unknown) => void = () => {}
    fetchCountries.mockReturnValue(new Promise((resolve) => (livrer = resolve)))
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Nouveau projet" }))
    const pays = (await screen.findByLabelText("Pays")) as HTMLSelectElement
    expect(pays.selectedOptions[0]?.textContent).toBe("Aucun pays disponible")

    livrer(page([togo, ivoire]))

    await waitFor(() => expect(screen.getByRole("option", { name: /Togo/ })).toBeInTheDocument())
    expect(pays.value).toBe("")
    fireEvent.change(screen.getByLabelText("Nom"), { target: { value: "Congrès" } })
    fireEvent.click(screen.getByRole("button", { name: "Créer" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Choisissez un pays.")
    expect(createProject).not.toHaveBeenCalled()
  })

  it("exige le type, puis ouvre la fiche du projet créé", async () => {
    fetchCountries.mockResolvedValue(page([togo]))
    createProject.mockResolvedValue({ ...congres, id: 12 })
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Nouveau projet" }))
    // Un seul pays : il est choisi d'office.
    await waitFor(() =>
      expect((screen.getByLabelText("Pays") as HTMLSelectElement).value).toBe(String(togo.id)),
    )
    fireEvent.change(screen.getByLabelText("Nom"), { target: { value: " Congrès de Kara " } })
    fireEvent.click(screen.getByRole("button", { name: "Créer" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Choisissez le type du projet.")

    fireEvent.change(screen.getByLabelText("Type de projet"), { target: { value: "congres" } })
    fireEvent.click(screen.getByRole("button", { name: "Créer" }))

    expect(await screen.findByText("Fiche du projet")).toBeInTheDocument()
    expect(createProject).toHaveBeenCalledWith({
      country: togo.id, name: "Congrès de Kara", kind: "congres", description: "",
    })
  })
})
