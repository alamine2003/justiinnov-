import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { Reallocations } from "./reallocations"
import type { Reallocation } from "@/lib/types"

const fetchReallocations = vi.fn()
vi.mock("@/lib/budgets", () => ({
  fetchReallocations: (...args: unknown[]) => fetchReallocations(...args),
  approveReallocation: vi.fn(),
  rejectReallocation: vi.fn(),
  createReallocation: vi.fn(),
}))

/**
 * Une demande telle que le serveur la rend : `can_decide` y tient compte de
 * l'état, du rôle et de l'auteur, le composant ne recopie aucune de ces
 * règles.
 */
function demande(overrides: Partial<Reallocation>): Reallocation {
  return {
    id: 1,
    source: 1,
    source_label: "Togo 2026",
    target: 2,
    target_label: "Bénin 2026",
    amount: "1000.00",
    reason: "Renfort",
    status: "pending",
    status_display: "En attente",
    requested_by: "dm.innov",
    decided_by: "",
    decided_at: null,
    decision_note: "",
    can_decide: true,
    created_at: "2026-03-15T10:00:00Z",
    updated_at: "2026-03-15T10:00:00Z",
    ...overrides,
  } as Reallocation
}

function afficher(rows: Reallocation[], canRequest = true) {
  fetchReallocations.mockResolvedValue({ count: rows.length, next: null, previous: null, results: rows })
  return render(<Reallocations budgets={[]} canRequest={canRequest} onChanged={vi.fn()} />)
}

describe("Reallocations — qui demande", () => {
  it("ne propose « Demander » qu'à qui a le droit de demander", async () => {
    afficher([], false)
    expect(await screen.findByText("Aucune réallocation")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Demander/ })).not.toBeInTheDocument()
  })
})

describe("Reallocations — qui tranche", () => {
  it("propose d'approuver ou de refuser quand le serveur ouvre la décision", async () => {
    afficher([demande({})])

    expect(await screen.findByRole("button", { name: "Approuver" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Refuser" })).toBeInTheDocument()
  })

  it("ne propose rien quand le serveur ferme la décision, fût-elle en attente", async () => {
    // Sa propre demande, ou un rôle qui ne tranche pas : le serveur l'a déjà dit.
    afficher([demande({ can_decide: false })])

    expect(await screen.findByText("Renfort")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Approuver" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Refuser" })).toBeNull()
  })

  it("ne propose rien sur une demande déjà tranchée", async () => {
    afficher([demande({ status: "approved", status_display: "Approuvée", can_decide: false })])

    expect(await screen.findByText("Renfort")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Approuver" })).toBeNull()
  })
})

describe("Reallocations — demander", () => {
  it("propose de demander un transfert à qui gère les enveloppes", async () => {
    afficher([], true)

    expect(await screen.findByRole("button", { name: "Demander" })).toBeInTheDocument()
  })

  it("ne le propose pas aux autres", async () => {
    afficher([], false)

    expect(await screen.findByText("Aucune réallocation")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Demander" })).toBeNull()
  })
})
