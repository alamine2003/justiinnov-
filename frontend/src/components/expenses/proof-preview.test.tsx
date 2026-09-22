import { render, screen } from "@testing-library/react"
import { beforeAll, describe, expect, it, vi } from "vitest"
import { ProofPreview } from "./proof-preview"
import type { Proof } from "@/lib/types"

vi.mock("@/lib/expenses", () => ({
  loadProofBlob: () => Promise.resolve({ url: "blob:http://localhost/facture", type: "application/pdf" }),
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

/**
 * Une pièce est un document reçu d'un tiers, affiché tel quel : le cadre qui
 * la montre ne doit pouvoir ni exécuter un script, ni soumettre un
 * formulaire, ni parler au nom de l'application. `sandbox` vide ferme tout ;
 * le lecteur PDF du navigateur n'en a pas besoin.
 */
describe("ProofPreview", () => {
  it("affiche un PDF dans un cadre sans aucun privilège", async () => {
    render(<ProofPreview proof={piece} onClose={() => {}} />)

    const cadre = await screen.findByTitle("facture.pdf")
    expect(cadre.tagName).toBe("IFRAME")
    expect(cadre).toHaveAttribute("sandbox", "")
    expect(cadre).toHaveAttribute("src", "blob:http://localhost/facture")
  })
})
