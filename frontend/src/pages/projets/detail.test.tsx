import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ProjetDetailPage } from "./detail"
import { invalidateReferentiel } from "@/lib/referentiel"

const fetchProject = vi.fn()
const fetchDossierKinds = vi.fn()
const fetchDossiers = vi.fn()
const createDossier = vi.fn()
vi.mock("@/lib/countries", () => ({
  fetchProject: (...args: unknown[]) => fetchProject(...args),
  fetchDossierKinds: (...args: unknown[]) => fetchDossierKinds(...args),
  fetchCountry: () => Promise.resolve({ teams: [], managers: [] }),
}))
vi.mock("@/lib/expenses", () => ({
  fetchDossiers: (...args: unknown[]) => fetchDossiers(...args),
  createDossier: (...args: unknown[]) => createDossier(...args),
}))
let droits: Record<string, boolean> = {}
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: { has_global_scope: false, countries: [], teams: [] },
    can: (cle: string) => droits[cle] ?? false,
  }),
}))

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })
const congres = {
  id: 7, country: 1, country_name: "Togo", name: "Congrès de Lomé", description: "",
  status: "active", status_display: "En cours", kind: "congres", kind_display: "Congrès",
  reference: "TG-P-2026-001", is_historical: false, a_typer: false, dossier_count: 0,
  accepte_des_dossiers: true, is_active: true,
}
const stands = { id: 3, project_kind: "congres", name: "Stands", is_active: true }
const collations = { id: 4, project_kind: "congres", name: "Collations", is_active: true }

function afficher() {
  return render(
    <MemoryRouter initialEntries={["/projets/7"]}>
      <Routes>
        <Route path="/projets/:id" element={<ProjetDetailPage />} />
        <Route path="/dossiers/:id" element={<p>Fiche du dossier</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  droits = { "expenses.create": true, "data.import": true }
  invalidateReferentiel()
  fetchProject.mockReset()
  fetchProject.mockResolvedValue(congres)
  fetchDossierKinds.mockReset()
  fetchDossierKinds.mockResolvedValue(page([stands, collations]))
  fetchDossiers.mockReset()
  fetchDossiers.mockResolvedValue(page([]))
  createDossier.mockReset()
})

describe("ProjetDetailPage", () => {
  it("liste les dossiers du projet et les filtre par type", async () => {
    afficher()
    expect(await screen.findByRole("heading", { name: "Congrès de Lomé" })).toBeInTheDocument()
    await waitFor(() =>
      expect(fetchDossiers).toHaveBeenCalledWith(
        expect.objectContaining({ project: 7, page: 1 }),
        expect.anything(),
      ),
    )

    fireEvent.click(await screen.findByRole("button", { name: /Collations/ }))

    await waitFor(() =>
      expect(fetchDossiers).toHaveBeenLastCalledWith(
        expect.objectContaining({ project: 7, kind: collations.id }),
        expect.anything(),
      ),
    )
  })

  it("propose l'import déjà dans ce projet", async () => {
    afficher()
    expect(await screen.findByRole("button", { name: "Importer" })).toHaveAttribute(
      "href",
      "/dossiers/import?project=7",
    )
  })

  it("n'ouvre pas de dossier dans un projet à typer, et dit pourquoi", async () => {
    fetchProject.mockResolvedValue({ ...congres, kind: "", a_typer: true, accepte_des_dossiers: false })
    afficher()

    expect(await screen.findByText(/n'a pas encore de type/)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Nouveau dossier" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Importer" })).toBeNull()
  })

  it("ne propose rien au siège, qui ne déclare pas", async () => {
    droits = {}
    afficher()

    await screen.findByRole("heading", { name: "Congrès de Lomé" })
    expect(screen.queryByRole("button", { name: "Nouveau dossier" })).toBeNull()
  })
})

describe("Nouveau dossier dans un projet", () => {
  it("le titre reprend le type choisi, puis la fiche du dossier s'ouvre", async () => {
    createDossier.mockResolvedValue({ id: 42 })
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Nouveau dossier" }))
    const type = await screen.findByLabelText("Type de dossier")
    await waitFor(() => expect(screen.getByRole("option", { name: "Stands" })).toBeInTheDocument())

    fireEvent.change(type, { target: { value: String(stands.id) } })
    expect(screen.getByLabelText("Libellé")).toHaveValue("Stands")
    fireEvent.click(screen.getByRole("button", { name: "Créer" }))

    expect(await screen.findByText("Fiche du dossier")).toBeInTheDocument()
    expect(createDossier).toHaveBeenCalledWith(
      expect.objectContaining({ project: 7, kind: stands.id, label: "Stands" }),
    )
    // Ni pays ni numéro : le serveur les tire du projet.
    expect(createDossier.mock.calls[0][0]).not.toHaveProperty("number")
    expect(createDossier.mock.calls[0][0]).not.toHaveProperty("country")
  })

  it("garde le titre écrit à la main quand le type change", async () => {
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Nouveau dossier" }))
    await waitFor(() => expect(screen.getByRole("option", { name: "Stands" })).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText("Libellé"), { target: { value: "Stands du hall A" } })
    fireEvent.change(screen.getByLabelText("Type de dossier"), { target: { value: String(stands.id) } })

    expect(screen.getByLabelText("Libellé")).toHaveValue("Stands du hall A")
  })

  it("exige un type avant d'envoyer", async () => {
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Nouveau dossier" }))
    fireEvent.click(await screen.findByRole("button", { name: "Créer" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Choisissez le type du dossier.")
    expect(createDossier).not.toHaveBeenCalled()
  })
})
