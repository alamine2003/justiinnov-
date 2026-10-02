import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ImportPage } from "./import"
import { invalidateReferentiel } from "@/lib/referentiel"

const fetchProjects = vi.fn()
const fetchDossierKinds = vi.fn()
const importExpenses = vi.fn()
vi.mock("@/lib/countries", () => ({
  fetchProjects: (...args: unknown[]) => fetchProjects(...args),
  fetchDossierKinds: (...args: unknown[]) => fetchDossierKinds(...args),
}))
vi.mock("@/lib/reporting", () => ({
  importExpenses: (...args: unknown[]) => importExpenses(...args),
}))

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })
const congres = {
  id: 7, name: "Congrès de Lomé", reference: "TG-P-2026-001", kind: "congres", accepte_des_dossiers: true,
}
const historique = {
  id: 8, name: "Historique (avant 2.0)", reference: "TG-P-HIST", kind: "", accepte_des_dossiers: false,
}
const stands = { id: 3, project_kind: "congres", name: "Stands", is_active: true }

function afficher(url = "/dossiers/import") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ImportPage />
    </MemoryRouter>,
  )
}

function choisirFichier() {
  const fichier = new File(["x"], "depenses.xlsx")
  fireEvent.change(screen.getByLabelText("Fichier"), { target: { files: [fichier] } })
  return fichier
}

beforeEach(() => {
  invalidateReferentiel()
  fetchProjects.mockReset()
  fetchProjects.mockResolvedValue(page([congres, historique]))
  fetchDossierKinds.mockReset()
  fetchDossierKinds.mockResolvedValue(page([stands]))
  importExpenses.mockReset()
  importExpenses.mockResolvedValue({
    dossiers_crees: 1, lignes_creees: 2, equipes_creees: 0, managers_crees: 0, erreurs: [], dry_run: true,
  })
})

describe("ImportPage — un classeur s'importe dans un projet (décision 102)", () => {
  it("ne propose que les projets qui acceptent des dossiers", async () => {
    afficher()
    await screen.findByRole("option", { name: /Congrès de Lomé/ })
    expect(screen.queryByRole("option", { name: /Historique/ })).toBeNull()
  })

  it("envoie le projet et le type, pas de pays", async () => {
    afficher()
    fireEvent.change(await screen.findByLabelText("Projet"), { target: { value: String(congres.id) } })
    await screen.findByRole("option", { name: "Stands" })
    fireEvent.change(screen.getByLabelText("Type de dossier"), { target: { value: String(stands.id) } })
    const fichier = choisirFichier()

    fireEvent.click(screen.getByRole("button", { name: "Simuler l'import" }))

    await waitFor(() => expect(importExpenses).toHaveBeenCalledOnce())
    expect(importExpenses).toHaveBeenCalledWith(fichier, {
      project: congres.id, kind: stands.id, dryRun: true,
    })
    expect(fetchDossierKinds).toHaveBeenCalledWith(expect.objectContaining({ project_kind: "congres" }))
  })

  it("reprend le projet de l'URL", async () => {
    afficher(`/dossiers/import?project=${congres.id}`)

    await waitFor(() =>
      expect((screen.getByLabelText("Projet") as HTMLSelectElement).value).toBe(String(congres.id)),
    )
    expect(await screen.findByRole("option", { name: "Stands" })).toBeInTheDocument()
  })

  it("laisse choisir quand le projet de l'URL n'accepte pas de dossier", async () => {
    afficher(`/dossiers/import?project=${historique.id}`)
    await screen.findByRole("option", { name: /Congrès de Lomé/ })
    expect((screen.getByLabelText("Projet") as HTMLSelectElement).value).toBe("")
    choisirFichier()

    fireEvent.click(screen.getByRole("button", { name: "Simuler l'import" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Choisissez le projet dans lequel importer.")
    expect(importExpenses).not.toHaveBeenCalled()
  })
})
