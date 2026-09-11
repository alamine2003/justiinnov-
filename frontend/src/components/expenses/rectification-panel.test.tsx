import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { RectificationPanel } from "./rectification-panel"
import type { Rectification } from "@/lib/types"

const approveRectification = vi.fn()
const refuseRectification = vi.fn()
vi.mock("@/lib/expenses", () => ({
  approveRectification: (...args: unknown[]) => approveRectification(...args),
  refuseRectification: (...args: unknown[]) => refuseRectification(...args),
}))

/**
 * Une demande telle que le serveur la rend : `can_decide` y tient compte de
 * l'état, du rôle et de l'auteur, le composant ne recopie aucune de ces
 * règles.
 */
function demande(overrides: Partial<Rectification>): Rectification {
  return {
    id: 3,
    expense: 7,
    expense_title: "Hôtel Sarakawa",
    expense_amount: "250000.00",
    expense_status: "justified",
    dossier: 12,
    dossier_number: "N-2026-012",
    country: 2,
    currency: "XOF",
    status: "pending",
    status_display: "En attente",
    motif: "Le montant justifie ne correspond pas a la facture.",
    previous_status: "justified",
    previous_status_display: "Justifié",
    previous_justified_amount: "250000.00",
    requested_by: "owner.togo",
    decided_by: "",
    decided_at: null,
    decision_note: "",
    can_decide: true,
    created_at: "2026-09-11T10:00:00Z",
    updated_at: "2026-09-11T10:00:00Z",
    ...overrides,
  } as Rectification
}

describe("RectificationPanel — affichage", () => {
  it("ne s'affiche pas sans demande", () => {
    const { container } = render(<RectificationPanel rows={[]} onDecided={vi.fn()} />)

    expect(container).toBeEmptyDOMElement()
  })

  it("montre ce que la demande conteste : la ligne, le constat, le motif", () => {
    render(<RectificationPanel rows={[demande({})]} currency="F CFA" onDecided={vi.fn()} />)

    expect(screen.getByText("Hôtel Sarakawa")).toBeInTheDocument()
    expect(screen.getByText("Justifié")).toBeInTheDocument()
    expect(screen.getByText(/250/)).toBeInTheDocument()
    expect(screen.getByText("Le montant justifie ne correspond pas a la facture.")).toBeInTheDocument()
    expect(screen.getByText(/owner\.togo/)).toBeInTheDocument()
  })
})

describe("RectificationPanel — qui tranche", () => {
  it("propose d'approuver ou de refuser quand le serveur ouvre la décision", () => {
    render(<RectificationPanel rows={[demande({})]} onDecided={vi.fn()} />)

    expect(screen.getByRole("button", { name: "Approuver la rectification" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Refuser" })).toBeInTheDocument()
  })

  it("ne propose rien quand le serveur ferme la décision, fût-elle en attente", () => {
    render(<RectificationPanel rows={[demande({ can_decide: false })]} onDecided={vi.fn()} />)

    expect(screen.queryByRole("button", { name: "Approuver la rectification" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Refuser" })).toBeNull()
  })

  it("approuve en un geste et prévient la page", async () => {
    approveRectification.mockResolvedValue(demande({ status: "approved" }))
    const onDecided = vi.fn().mockResolvedValue(undefined)
    render(<RectificationPanel rows={[demande({})]} onDecided={onDecided} />)

    fireEvent.click(screen.getByRole("button", { name: "Approuver la rectification" }))

    await waitFor(() => expect(approveRectification).toHaveBeenCalledWith(3))
    await waitFor(() => expect(onDecided).toHaveBeenCalled())
  })

  it("exige un motif pour refuser, puis le transmet", async () => {
    refuseRectification.mockResolvedValue(demande({ status: "refused" }))
    const onDecided = vi.fn().mockResolvedValue(undefined)
    render(<RectificationPanel rows={[demande({})]} onDecided={onDecided} />)

    fireEvent.click(screen.getByRole("button", { name: "Refuser" }))
    const dialogue = screen.getByRole("dialog")
    expect(dialogue).toHaveTextContent("Hôtel Sarakawa")
    fireEvent.click(screen.getAllByRole("button", { name: "Refuser" }).at(-1)!)
    expect(screen.getByRole("alert")).toHaveTextContent("motiv")
    expect(refuseRectification).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText("Motif du refus"), {
      target: { value: "  La facture fait bien 250 000.  " },
    })
    fireEvent.click(screen.getAllByRole("button", { name: "Refuser" }).at(-1)!)

    await waitFor(() =>
      expect(refuseRectification).toHaveBeenCalledWith(3, "La facture fait bien 250 000."),
    )
    await waitFor(() => expect(onDecided).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("affiche le refus du serveur sans fermer le dialogue", async () => {
    refuseRectification.mockRejectedValue(new Error("Cette demande a deja ete traitee."))
    render(<RectificationPanel rows={[demande({})]} onDecided={vi.fn()} />)

    fireEvent.click(screen.getByRole("button", { name: "Refuser" }))
    fireEvent.change(screen.getByLabelText("Motif du refus"), { target: { value: "Non" } })
    fireEvent.click(screen.getAllByRole("button", { name: "Refuser" }).at(-1)!)

    expect(await screen.findByRole("alert")).toHaveTextContent("Cette demande a deja ete traitee.")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })
})
