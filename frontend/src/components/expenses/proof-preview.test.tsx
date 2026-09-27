import { render, screen } from "@testing-library/react"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import { ProofPreview } from "./proof-preview"
import { loadProofBlob } from "@/lib/expenses"
import type { Proof } from "@/lib/types"

vi.mock("@/lib/expenses", () => ({
  loadProofBlob: vi.fn(),
  downloadProof: vi.fn(),
}))

const piece = {
  id: 4,
  original_name: "facture.pdf",
  kind_display: "Facture",
  version: 1,
  sha256: "0123456789abcdef0123456789abcdef",
  content_type: "application/pdf",
} as unknown as Proof

beforeAll(() => {
  // jsdom ne connaît pas les URL d'objet ; la fenêtre les révoque à la fermeture.
  URL.revokeObjectURL ??= () => {}
})

beforeEach(() => {
  vi.mocked(loadProofBlob).mockReset()
})

/**
 * Une pièce est un document reçu d'un tiers, affiché tel quel : le cadre qui
 * la montre ne doit pouvoir ni exécuter un script, ni soumettre un
 * formulaire, ni parler au nom de l'application. `sandbox` vide ferme tout —
 * sauf pour un PDF, que Chrome refuse d'ouvrir dans un bac à sable.
 */
describe("ProofPreview", () => {
  it("affiche un PDF hors bac à sable, où le lecteur du navigateur peut l'ouvrir", async () => {
    vi.mocked(loadProofBlob).mockResolvedValue({
      url: "blob:http://localhost/facture",
      type: "application/pdf",
    })
    render(<ProofPreview proof={piece} onClose={() => {}} />)

    const cadre = await screen.findByTitle("facture.pdf")
    expect(cadre.tagName).toBe("IFRAME")
    // Avec `sandbox`, Chrome n'affiche qu'une icône de document triste
    // (production, 27 septembre 2026).
    expect(cadre).not.toHaveAttribute("sandbox")
    expect(cadre).toHaveAttribute("src", "blob:http://localhost/facture")
  })

  it("garde tout autre document dans un cadre sans aucun privilège", async () => {
    vi.mocked(loadProofBlob).mockResolvedValue({
      url: "blob:http://localhost/releve",
      type: "text/plain",
    })
    render(<ProofPreview proof={{ ...piece, original_name: "releve.txt" }} onClose={() => {}} />)

    const cadre = await screen.findByTitle("releve.txt")
    expect(cadre).toHaveAttribute("sandbox", "")
  })
})
