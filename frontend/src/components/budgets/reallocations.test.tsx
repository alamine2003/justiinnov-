import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { Reallocations } from "./reallocations"
import type { Budget, Reallocation } from "@/lib/types"

const fetchReallocations = vi.fn()
const createReallocation = vi.fn()
vi.mock("@/lib/budgets", () => ({
  fetchReallocations: (...args: unknown[]) => fetchReallocations(...args),
  approveReallocation: vi.fn(),
  rejectReallocation: vi.fn(),
  createReallocation: (...args: unknown[]) => createReallocation(...args),
}))

/** Une enveloppe telle que la page des budgets la passe au formulaire. */
function enveloppe(id: number, country_name: string): Budget {
  return {
    id,
    country: id,
    country_name,
    year: 2026,
    scope_kind: "country",
    scope_label: null,
    currency: "XOF",
    amount: "1000.00",
    figures: { remaining: "800.00", execution_rate: "0.2", execution_level: "ok" },
    is_active: true,
  } as unknown as Budget
}

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
    requested_by: "rh.innov",
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

/**
 * Régression : le formulaire pré-remplissait source et cible avec les deux
 * premières enveloppes *au montage*. Ouvert avant que la liste n'arrive, il
 * gardait une cible vide que le navigateur masquait — la première option
 * s'affichait comme choisie — et `target: ""` partait au serveur.
 */
describe("Reallocations — formulaire ouvert avant les enveloppes", () => {
  beforeEach(() => {
    createReallocation.mockReset()
  })

  it("laisse le choix vide quand la liste arrive, et n'envoie pas une cible vide", async () => {
    fetchReallocations.mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
    const { rerender } = render(
      <Reallocations budgets={[]} canRequest onChanged={vi.fn()} />,
    )
    fireEvent.click(await screen.findByRole("button", { name: "Demander" }))
    await screen.findByLabelText("Enveloppe source")

    rerender(
      <Reallocations
        budgets={[enveloppe(1, "Togo"), enveloppe(2, "Benin")]}
        canRequest
        onChanged={vi.fn()}
      />,
    )

    const source = screen.getByLabelText("Enveloppe source") as HTMLSelectElement
    const cible = screen.getByLabelText("Enveloppe destinataire") as HTMLSelectElement
    // Une option vide, explicite, est bien celle qui s'affiche.
    expect(cible.value).toBe("")
    expect(cible.selectedOptions[0]?.textContent).toBe("Choisissez une enveloppe…")

    fireEvent.change(source, { target: { value: "1" } })
    fireEvent.change(screen.getByLabelText("Montant"), { target: { value: "100" } })
    fireEvent.change(screen.getByLabelText("Justification"), { target: { value: "Renfort" } })
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }))

    expect(
      await screen.findByText("Choisissez l'enveloppe source et l'enveloppe destinataire."),
    ).toBeInTheDocument()
    expect(createReallocation).not.toHaveBeenCalled()

    fireEvent.change(cible, { target: { value: "2" } })
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }))

    await waitFor(() => expect(createReallocation).toHaveBeenCalledOnce())
    expect(createReallocation.mock.calls[0][0]).toMatchObject({ source: 1, target: 2 })
  })
})
