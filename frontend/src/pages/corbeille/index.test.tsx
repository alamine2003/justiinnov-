import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { CorbeillePage } from "./index"
import { invalidateReferentiel } from "@/lib/referentiel"
import type { ElementSupprime } from "@/lib/types"

const { fetchCorbeille, telechargerDepuisLaCorbeille } = vi.hoisted(() => ({
  fetchCorbeille: vi.fn(),
  telechargerDepuisLaCorbeille: vi.fn(),
}))
vi.mock("@/lib/corbeille", () => ({ fetchCorbeille, telechargerDepuisLaCorbeille }))
vi.mock("@/lib/countries", () => ({
  fetchCountries: vi.fn(() => Promise.resolve({ count: 0, results: [] })),
}))
let ouverte = true
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ me: { workflow: { suppressions_ouvertes: ouverte } }, can: () => true }),
}))

function element(extra: Partial<ElementSupprime>): ElementSupprime {
  return {
    id: 1, nature: "dossier", nature_display: "Dossier", objet_id: 11,
    reference: "TG-P-2026-001-D001", libelle: "Stands", country: 2, country_name: "Togo",
    montant: null, devise: "", donnees: {}, sha256: "", racine: null, emportes: 0,
    motif: "Saisie d'essai", supprime_par: "direction.demo",
    supprime_le: "2026-10-07T10:00:00Z", download_url: null,
    ...extra,
  } as ElementSupprime
}

function page(results: ElementSupprime[]) {
  return { count: results.length, next: null, previous: null, results }
}

beforeEach(() => {
  ouverte = true
  invalidateReferentiel()
  fetchCorbeille.mockReset()
  telechargerDepuisLaCorbeille.mockReset()
})

describe("CorbeillePage (décision 120)", () => {
  it("liste ce qui a été choisi, et ce que chaque élément a emporté", async () => {
    const piece = element({
      id: 3, nature: "piece", nature_display: "Justificatif", libelle: "recu.pdf",
      racine: 1, download_url: "/api/corbeille/3/fichier/",
    })
    fetchCorbeille.mockImplementation((params: Record<string, unknown>) =>
      Promise.resolve(params.racine ? page([piece]) : page([element({ emportes: 2 })])),
    )

    render(<CorbeillePage />)

    expect(await screen.findByText("Stands")).toBeInTheDocument()
    expect(screen.getByText(/avec 2 éléments/)).toBeInTheDocument()
    expect(screen.getByText("Saisie d'essai")).toBeInTheDocument()
    expect(fetchCorbeille).toHaveBeenCalledWith(expect.objectContaining({ tetes: true }), expect.anything())

    fireEvent.click(screen.getByRole("button", { name: "Voir ce qui est parti avec « Stands »" }))

    expect(await screen.findByText("recu.pdf")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Télécharger le justificatif « recu.pdf »" }))
    await waitFor(() => expect(telechargerDepuisLaCorbeille).toHaveBeenCalledWith(piece))
  })

  it("dit quand elle est vide, et que les suppressions sont fermées", async () => {
    ouverte = false
    fetchCorbeille.mockResolvedValue(page([]))

    render(<CorbeillePage />)

    expect(await screen.findByText("La corbeille est vide")).toBeInTheDocument()
    expect(screen.getByText(/Les suppressions sont fermées/)).toBeInTheDocument()
  })

  it("filtre par nature, et revient à la première page", async () => {
    fetchCorbeille.mockResolvedValue(page([]))
    render(<CorbeillePage />)
    await screen.findByText("La corbeille est vide")

    fireEvent.change(screen.getByLabelText("Filtrer par nature"), { target: { value: "ligne" } })

    await waitFor(() =>
      expect(fetchCorbeille).toHaveBeenLastCalledWith(
        expect.objectContaining({ nature: "ligne", page: 1, tetes: true }),
        expect.anything(),
      ),
    )
  })
})
