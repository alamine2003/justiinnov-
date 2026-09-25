import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ManageBeneficiaries } from "./manage-beneficiaries"
import type { Beneficiary } from "@/lib/types"

const fetchBeneficiaries = vi.fn()
vi.mock("@/lib/expenses", () => ({
  fetchBeneficiaries: (...args: unknown[]) => fetchBeneficiaries(...args),
  createBeneficiary: vi.fn(),
  updateBeneficiary: vi.fn(),
}))

function beneficiaire(overrides: Partial<Beneficiary>): Beneficiary {
  return {
    id: 1, country: 1, country_name: "Togo", name: "Pharmacie", kind: "client",
    kind_display: "Client", phone: "", email: "", contact: "",
    contact_manquant: false, is_active: true,
    created_at: "2026-09-25T10:00:00Z", updated_at: "2026-09-25T10:00:00Z",
    ...overrides,
  } as Beneficiary
}

describe("ManageBeneficiaries", () => {
  it("montre les coordonnées, et signale celui qui n'en a pas", async () => {
    fetchBeneficiaries.mockResolvedValue({
      count: 2, next: null, previous: null,
      results: [
        beneficiaire({ id: 1, name: "Pharmacie du Port", phone: "+228 90 00 00 00", email: "port@exemple.org" }),
        beneficiaire({ id: 2, name: "Clinique de Kara", contact_manquant: true }),
      ],
    })

    render(<ManageBeneficiaries countryId={91} canManage={false} />)

    expect(await screen.findByText("+228 90 00 00 00 · port@exemple.org")).toBeInTheDocument()
    // Le serveur le dit (`contact_manquant`) ; l'écran ne le déduit pas.
    expect(screen.getByText("À compléter")).toBeInTheDocument()
    expect(screen.getAllByText("À compléter")).toHaveLength(1)
  })
})
