import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ProjectTypesSection } from "./project-types-section"

const fetchProjectTypes = vi.fn()
const fetchDossierKinds = vi.fn()
const createProjectType = vi.fn()
const updateProjectType = vi.fn()
const createDossierKind = vi.fn()
const updateDossierKind = vi.fn()
vi.mock("@/lib/countries", () => ({
  fetchProjectTypes: (...args: unknown[]) => fetchProjectTypes(...args),
  fetchDossierKinds: (...args: unknown[]) => fetchDossierKinds(...args),
  createProjectType: (...args: unknown[]) => createProjectType(...args),
  updateProjectType: (...args: unknown[]) => updateProjectType(...args),
  createDossierKind: (...args: unknown[]) => createDossierKind(...args),
  updateDossierKind: (...args: unknown[]) => updateDossierKind(...args),
}))
let droits: Record<string, boolean> = {}
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ can: (cle: string) => droits[cle] ?? false }),
}))

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })
const congres = {
  id: 1, code: "congres", name: "Congrès", name_en: "Congress", libelle: "Congrès",
  description: "", ordre: 1, is_active: true, dossier_kinds_actifs: 1, projets: 3,
}
const formation = {
  id: 4, code: "formation", name: "Formation", name_en: "", libelle: "Formation",
  description: "", ordre: 4, is_active: true, dossier_kinds_actifs: 0, projets: 0,
}
const stands = {
  id: 3, project_kind: "congres", project_kind_display: "Congrès", name: "Stands",
  description: "", ordre: 1, is_active: true,
}

function afficher() {
  return render(
    <MemoryRouter>
      <ProjectTypesSection />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  for (const mock of [
    fetchProjectTypes, fetchDossierKinds, createProjectType, updateProjectType,
    createDossierKind, updateDossierKind,
  ]) mock.mockReset()
  fetchProjectTypes.mockResolvedValue(page([congres, formation]))
  fetchDossierKinds.mockResolvedValue(page([stands]))
})

describe("Types de projets et leurs dossiers (décision 119)", () => {
  it("range chaque type de dossier sous son type de projet, en lecture pour l'administrateur", async () => {
    droits = { "configuration.manage": true }
    afficher()

    const carte = (await screen.findByRole("heading", { name: "Congrès" })).closest("div.space-y-3")!
    expect(within(carte as HTMLElement).getByText("Stands")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Ajouter un type de projet/ })).toBeNull()
    expect(screen.queryByRole("button", { name: /Modifier le type de projet/ })).toBeNull()
  })

  it("signale un type de projet sans type de dossier actif : il n'ouvre pas de projet", async () => {
    droits = {}
    afficher()

    expect(await screen.findByText(/Aucun dossier actif/)).toBeInTheDocument()
  })

  it("crée un type de projet, sans motif, pour le super administrateur", async () => {
    droits = { "project_types.manage": true, "dossier_kinds.manage": true }
    createProjectType.mockResolvedValue(formation)
    afficher()
    await screen.findByRole("heading", { name: "Congrès" })

    fireEvent.click(screen.getByRole("button", { name: /Ajouter un type de projet/ }))
    fireEvent.change(await screen.findByLabelText(/^Nom$/), { target: { value: "Séminaire" } })
    fireEvent.change(screen.getByLabelText(/Nom en anglais/), { target: { value: "Seminar" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() =>
      expect(createProjectType).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Séminaire", name_en: "Seminar", is_active: true }),
      ),
    )
    expect(createProjectType.mock.calls[0][0]).not.toHaveProperty("motif")
  })

  it("exige un motif pour modifier un type de projet, et l'envoie", async () => {
    droits = { "project_types.manage": true }
    updateProjectType.mockResolvedValue(congres)
    afficher()

    fireEvent.click(await screen.findByRole("button", { name: /Modifier le type de projet « Congrès »/ }))
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(/motif/)
    expect(updateProjectType).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/Motif/), { target: { value: "Terme de la direction" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() =>
      expect(updateProjectType).toHaveBeenCalledWith(
        1, expect.objectContaining({ motif: "Terme de la direction", ordre: 1 }),
      ),
    )
  })

  it("ajoute un type de dossier sous son type de projet, avec son ordre", async () => {
    droits = { "dossier_kinds.manage": true }
    createDossierKind.mockResolvedValue(stands)
    afficher()
    await screen.findByRole("heading", { name: "Formation" })

    fireEvent.click(screen.getAllByRole("button", { name: /Ajouter un type de dossier/ })[1])
    fireEvent.change(await screen.findByLabelText(/^Type de dossier$/), { target: { value: "Salles" } })
    fireEvent.change(screen.getByLabelText(/^Ordre$/), { target: { value: "2" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() =>
      expect(createDossierKind).toHaveBeenCalledWith(
        expect.objectContaining({ project_kind: "formation", name: "Salles", ordre: 2 }),
      ),
    )
  })

  it("affiche sous le champ l'erreur que le serveur renvoie", async () => {
    droits = { "project_types.manage": true }
    const { ApiError } = await import("@/lib/api")
    createProjectType.mockRejectedValue(
      new ApiError(400, "Requête invalide", { name: ["Ce type de projet existe déjà."] }),
    )
    afficher()
    await screen.findByRole("heading", { name: "Congrès" })

    fireEvent.click(screen.getByRole("button", { name: /Ajouter un type de projet/ }))
    fireEvent.change(await screen.findByLabelText(/^Nom$/), { target: { value: "Congrès" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    expect(await screen.findByText("Ce type de projet existe déjà.")).toBeInTheDocument()
  })
})
