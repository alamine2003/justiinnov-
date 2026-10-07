import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { CarteDeLigne } from "./expense-line-card"
import type { Expense, Proof } from "@/lib/types"

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ can: () => false, me: { username: "owner.togo" } }),
}))
vi.mock("@/lib/accounts", () => ({ fetchConfiguration: vi.fn() }))

function ligne(overrides: Partial<Expense> = {}): Expense {
  return {
    id: 9, dossier: 3, title: "Taxi", amount: "5000.00", justified_amount: "0.00", gap: "5000.00",
    status: "submitted", status_display: "Soumise", country_timezone: "Africa/Lome",
    date: "2026-03-15T10:00:00Z", allowed_actions: [], has_proof: false,
    original_currency: "", original_amount: null, payment_method_display: "",
    ...overrides,
  } as unknown as Expense
}

const piece = {
  id: 1, dossier: 3, expense: 9, original_name: "taxi.pdf", kind: "receipt",
  kind_display: "Reçu", status: "received", status_display: "Reçu", version: 1,
  size: 10, sha256: "a".repeat(64), allowed_reviews: [], created_at: "2026-03-15T10:00:00Z",
} as unknown as Proof

function afficher(expense: Expense, proofs: Proof[] = []) {
  return render(
    <ul>
      <CarteDeLigne
        expense={expense}
        proofs={proofs}
        closed={false}
        currency="FCFA"
        deleting={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onTransition={vi.fn()}
        onRequestRectification={vi.fn()}
        onError={vi.fn()}
        onProofsChanged={vi.fn()}
      />
    </ul>,
  )
}

describe("CarteDeLigne — le justificatif de la ligne (décision 107)", () => {
  it("dit « Sans justificatif » quand le serveur le dit", () => {
    afficher(ligne({ has_proof: false }))

    expect(screen.getByText("Sans justificatif")).toBeInTheDocument()
  })

  it("montre la pièce de la ligne quand elle est prouvée", () => {
    afficher(ligne({ has_proof: true }), [piece])

    expect(screen.queryByText("Sans justificatif")).toBeNull()
    expect(screen.getByText("taxi.pdf")).toBeInTheDocument()
  })

  it("propose le dépôt seulement avec `upload` dans les actions de la ligne", () => {
    const { unmount } = afficher(ligne({ allowed_actions: [] }))
    expect(screen.queryByRole("button", { name: /Déposer/ })).toBeNull()
    unmount()

    afficher(ligne({ allowed_actions: ["upload"] as Expense["allowed_actions"] }))
    // Nommé par sa ligne : chaque carte a le sien.
    expect(screen.getByRole("button", { name: "Déposer la pièce de « Taxi »" })).toBeInTheDocument()
  })

  it("nomme le dépôt d'une pièce de plus par son texte visible (WCAG 2.5.3)", () => {
    afficher(ligne({ has_proof: true, allowed_actions: ["upload"] as Expense["allowed_actions"] }), [piece])

    // Le bouton dit « Déposer une autre pièce » : son nom accessible le
    // reprend, au lieu de « Déposer la pièce de… », qu'un utilisateur de
    // commande vocale ne pouvait pas prononcer en lisant l'écran.
    const bouton = screen.getByRole("button", { name: "Déposer une autre pièce pour « Taxi »" })
    expect(bouton).toHaveTextContent("Déposer une autre pièce")
  })
})
