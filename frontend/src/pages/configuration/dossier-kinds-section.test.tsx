import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DossierKindsSection } from "./dossier-kinds-section"

const fetchDossierKinds = vi.fn()
const updateDossierKind = vi.fn()
vi.mock("@/lib/countries", () => ({
  fetchDossierKinds: (...args: unknown[]) => fetchDossierKinds(...args),
  updateDossierKind: (...args: unknown[]) => updateDossierKind(...args),
  createDossierKind: vi.fn(),
}))
let droits: Record<string, boolean> = {}
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ can: (cle: string) => droits[cle] ?? false }),
}))

const stands = {
  id: 3, project_kind: "congres", project_kind_display: "Congrès", name: "Stands",
  description: "", is_active: true,
}

beforeEach(() => {
  fetchDossierKinds.mockReset()
  fetchDossierKinds.mockResolvedValue({ count: 1, next: null, previous: null, results: [stands] })
  updateDossierKind.mockReset()
})

describe("Types de dossiers (décision 108)", () => {
  it("se lit sans pouvoir se modifier sans `dossier_kinds.manage`", async () => {
    droits = { "configuration.manage": true }
    render(<DossierKindsSection />)

    expect(await screen.findByText("Stands")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Ajouter" })).toBeNull()
  })

  it("envoie le motif d'une modification, pour le super administrateur", async () => {
    droits = { "dossier_kinds.manage": true }
    updateDossierKind.mockResolvedValue(stands)
    render(<DossierKindsSection />)
    await screen.findByText("Stands")

    fireEvent.click(screen.getByRole("button", { name: /Modifier/ }))
    fireEvent.change(await screen.findByLabelText(/Motif/), { target: { value: "Plus de stands" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() =>
      expect(updateDossierKind).toHaveBeenCalledWith(3, expect.objectContaining({ motif: "Plus de stands" })),
    )
  })
})
