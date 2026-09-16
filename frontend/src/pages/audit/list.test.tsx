import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AuditPage } from "./list"
import type { AuditEntry } from "@/lib/types"

const fetchAudit = vi.fn()
vi.mock("@/lib/expenses", () => ({ fetchAudit: (...args: unknown[]) => fetchAudit(...args) }))
vi.mock("@/lib/countries", () => ({
  fetchCountries: vi.fn(() => Promise.resolve({ count: 0, results: [] })),
}))
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ me: { has_global_scope: true }, can: () => true }),
}))

function entree(detail: Record<string, unknown>): AuditEntry {
  return {
    id: 1,
    user: "rh.innov",
    action: "submitted",
    action_display: "Soumis",
    object_type: "Expense",
    object_id: 7,
    label: "Hôtel Abidjan",
    country: 1,
    country_name: "Côte d'Ivoire",
    detail,
    ip_address: "10.0.0.1",
    user_agent: "",
    created_at: "2026-03-15T08:30:00Z",
  } as unknown as AuditEntry
}

beforeEach(() => fetchAudit.mockReset())

/**
 * Régression : le détail d'une entrée sortait brut — « draft → submitted » et
 * « 1500.00 → 1200.00 », en français comme en anglais. La règle « aucune
 * chaîne visible en dur » était contournée parce que la chaîne venait de la
 * donnée plutôt que du code, et le garde-fou anti-chaînes-en-dur ne voit que
 * les accents.
 */
describe("Journal d'audit — détail d'une entrée", () => {
  it("traduit les statuts du circuit", async () => {
    fetchAudit.mockResolvedValue({
      count: 1,
      results: [entree({ from_status: "draft", to_status: "submitted" })],
    })

    render(<AuditPage />)

    await waitFor(() => expect(screen.getByText("Brouillon → Soumis")).toBeInTheDocument())
    expect(screen.queryByText("draft → submitted")).toBeNull()
  })

  it("formate les montants", async () => {
    fetchAudit.mockResolvedValue({
      count: 1,
      results: [
        entree({ before: { amount: "1500000.00" }, after: { amount: "1200000.00" } }),
      ],
    })

    render(<AuditPage />)

    await waitFor(() => expect(fetchAudit).toHaveBeenCalled())
    // Le montant passe par `formatAmount` : séparateurs de milliers, pas de
    // décimales inutiles.
    expect(screen.getByText(/1 500 000/)).toBeInTheDocument()
    expect(screen.queryByText(/1500000\.00/)).toBeNull()
  })
})
