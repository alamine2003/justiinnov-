import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ProjetDetailPage } from "./detail"
import { invalidateReferentiel } from "@/lib/referentiel"
import { pageDesTypesDeProjets } from "@/test/types-de-projets-fixtures"

const fetchProject = vi.fn()
const fetchDossierKinds = vi.fn()
const fetchDossiers = vi.fn()
const renameProject = vi.fn()
const updateProject = vi.fn()
const completerProject = vi.fn()
const fetchProjectHistory = vi.fn()
vi.mock("@/lib/countries", () => ({
  fetchProject: (...args: unknown[]) => fetchProject(...args),
  fetchDossierKinds: (...args: unknown[]) => fetchDossierKinds(...args),
  fetchCountry: () => Promise.resolve({ teams: [], managers: [] }),
  renameProject: (...args: unknown[]) => renameProject(...args),
  updateProject: (...args: unknown[]) => updateProject(...args),
  completerProject: (...args: unknown[]) => completerProject(...args),
  fetchProjectHistory: (...args: unknown[]) => fetchProjectHistory(...args),
  fetchProjectTypes: () => pageDesTypesDeProjets(),
}))
vi.mock("@/lib/expenses", () => ({
  fetchDossiers: (...args: unknown[]) => fetchDossiers(...args),
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

function afficher(adresse = "/projets/7") {
  return render(
    <MemoryRouter initialEntries={[adresse]}>
      <Routes>
        <Route path="/projets/:id" element={<ProjetDetailPage />} />
        <Route path="/dossiers/:id" element={<p>Fiche du dossier</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  droits = { "expenses.create": true, "data.import": true, "projets.rename": true }
  invalidateReferentiel()
  fetchProject.mockReset()
  fetchProject.mockResolvedValue(congres)
  fetchDossierKinds.mockReset()
  fetchDossierKinds.mockResolvedValue(page([stands, collations]))
  fetchDossiers.mockReset()
  fetchDossiers.mockResolvedValue(page([]))
  renameProject.mockReset()
  updateProject.mockReset()
  completerProject.mockReset()
  fetchProjectHistory.mockReset()
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

  it("n'importe pas dans un projet à typer, et dit pourquoi", async () => {
    fetchProject.mockResolvedValue({ ...congres, kind: "", a_typer: true, accepte_des_dossiers: false })
    afficher()

    expect(await screen.findByText(/n'a pas encore de type/)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Importer" })).toBeNull()
  })

  it("n'ouvre jamais de dossier à la main : le projet est né avec les siens", async () => {
    afficher()

    await screen.findByRole("heading", { name: "Congrès de Lomé" })
    expect(screen.queryByRole("button", { name: "Nouveau dossier" })).toBeNull()
  })
})

describe("Renommer le projet, côté pays", () => {
  it("exige un motif, puis affiche le nouveau titre", async () => {
    renameProject.mockResolvedValue({ ...congres, name: "Congrès de Lomé 2026" })
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Renommer" }))
    fireEvent.change(screen.getByLabelText("Nom"), { target: { value: "Congrès de Lomé 2026" } })
    fireEvent.click(screen.getByRole("button", { name: "Renommer" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Indiquez le motif")
    expect(renameProject).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "Année oubliée" } })
    fireEvent.click(screen.getByRole("button", { name: "Renommer" }))

    expect(await screen.findByRole("heading", { name: "Congrès de Lomé 2026" })).toBeInTheDocument()
    expect(renameProject).toHaveBeenCalledWith(7, "Congrès de Lomé 2026", "Année oubliée")
  })

  it("garde le dialogue ouvert sur un refus du serveur", async () => {
    const { ApiError } = await import("@/lib/api")
    renameProject.mockRejectedValue(
      new ApiError(400, "Requête invalide", { name: ["Ce projet existe déjà pour ce pays."] }),
    )
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Renommer" }))
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "Doublon" } })
    fireEvent.click(screen.getByRole("button", { name: "Renommer" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Ce projet existe déjà pour ce pays.")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("n'est pas proposé sans le droit", async () => {
    droits = {}
    afficher()

    await screen.findByRole("heading", { name: "Congrès de Lomé" })
    expect(screen.queryByRole("button", { name: "Renommer" })).toBeNull()
  })
})

describe("Modifier et compléter le projet, côté siège", () => {
  beforeEach(() => {
    droits = { "projets.update": true, "audit.read": true }
  })

  it("modifie sans jamais toucher au titre, motif à l'appui", async () => {
    updateProject.mockResolvedValue({ ...congres, status: "completed", status_display: "Terminé" })
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Modifier" }))
    expect(screen.queryByLabelText("Nom")).toBeNull()
    fireEvent.change(screen.getByLabelText("Statut"), { target: { value: "completed" } })
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "Congrès tenu" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(updateProject).toHaveBeenCalled())
    const [id, donnees] = updateProject.mock.calls[0]
    expect(id).toBe(7)
    expect(donnees).toMatchObject({ status: "completed", motif: "Congrès tenu" })
    expect(donnees).not.toHaveProperty("name")
    expect(donnees).not.toHaveProperty("kind")
  })

  it("type un projet d'avant la 2.0", async () => {
    const aTyper = { ...congres, kind: "", a_typer: true, accepte_des_dossiers: false }
    fetchProject.mockResolvedValue(aTyper)
    updateProject.mockResolvedValue({ ...congres })
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Modifier" }))
    // Les types viennent du serveur (décision 119).
    await screen.findByRole("option", { name: "Voyage" })
    fireEvent.change(screen.getByLabelText("Type de projet"), { target: { value: "voyage" } })
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "Reprise" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() =>
      expect(updateProject).toHaveBeenCalledWith(7, expect.objectContaining({ kind: "voyage" })),
    )
  })

  it("complète le projet de ses dossiers manquants, après confirmation", async () => {
    completerProject.mockResolvedValue(congres)
    afficher()
    fireEvent.click(await screen.findByRole("button", { name: "Compléter les dossiers" }))
    fireEvent.click(screen.getByRole("button", { name: "Compléter" }))

    await waitFor(() => expect(completerProject).toHaveBeenCalledWith(7))
    await waitFor(() => expect(fetchDossiers.mock.calls.length).toBeGreaterThan(1))
  })

  it("ne propose ni Renommer ni Nouveau dossier au siège", async () => {
    afficher()

    await screen.findByRole("button", { name: "Modifier" })
    expect(screen.queryByRole("button", { name: "Renommer" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Nouveau dossier" })).toBeNull()
  })

  it("l'onglet Historique relit le journal du projet", async () => {
    fetchProjectHistory.mockResolvedValue({
      tronque: false,
      entrees: [
        {
          source: "referentiel", id: 1, action: "updated", action_display: "Mise à jour",
          objet: "Projet", object_id: 7, label: "Congrès de Lomé", user: "owner.togo",
          ip_address: "10.0.0.2", motif: "Année oubliée",
          avant: { name: "Congrès de Lomé" }, apres: { name: "Congrès de Lomé 2026" },
          note: "", created_at: "2026-10-01T08:00:00Z",
        },
      ],
    })
    afficher("/projets/7?onglet=historique")

    expect(await screen.findByText("Année oubliée")).toBeInTheDocument()
    expect(screen.getByText("Congrès de Lomé 2026")).toBeInTheDocument()
    expect(fetchProjectHistory).toHaveBeenCalledWith(7, expect.anything())
  })
})

describe("Historique du projet", () => {
  it("n'existe pas sans audit.read", async () => {
    afficher("/projets/7?onglet=historique")

    await screen.findByRole("heading", { name: "Congrès de Lomé" })
    expect(screen.queryByRole("tab", { name: "Historique" })).toBeNull()
    expect(fetchProjectHistory).not.toHaveBeenCalled()
  })
})
