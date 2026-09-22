import { render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { RatesSection } from "./rates-section"
import type { ExchangeRate } from "@/lib/types"

const fetchExchangeRates = vi.fn()
vi.mock("@/lib/budgets", () => ({
  fetchExchangeRates: (...args: unknown[]) => fetchExchangeRates(...args),
  createExchangeRate: vi.fn(),
}))
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ can: () => true }),
}))

function taux(overrides: Partial<ExchangeRate>): ExchangeRate {
  return {
    id: 1,
    currency: "EUR",
    rate_to_xof: "655.957",
    valid_from: "2026-01-01",
    is_current: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  }
}

/**
 * Régression : « en vigueur » était déduit du tri — le premier taux de
 * chaque devise. Un taux publié pour le mois prochain, trié en tête,
 * s'affichait donc en vigueur alors que l'ancien s'appliquait encore. Le
 * serveur tranche (`is_current`) et l'écran le lit.
 */
describe("RatesSection — taux en vigueur", () => {
  it("suit `is_current` du serveur, pas l'ordre de la liste", async () => {
    fetchExchangeRates.mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [
        taux({ id: 2, valid_from: "2099-01-01", is_current: false }),
        taux({ id: 1, valid_from: "2026-01-01", is_current: true }),
      ],
    })

    render(<RatesSection />)

    await screen.findByText("en vigueur")
    const [futur, courant] = screen.getAllByRole("row").slice(1)
    expect(within(futur).getByText(/2099/)).toBeInTheDocument()
    expect(within(futur).getByText("historique")).toBeInTheDocument()
    expect(within(futur).queryByText("en vigueur")).toBeNull()
    expect(within(courant).getByText("en vigueur")).toBeInTheDocument()
  })
})
