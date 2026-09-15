import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ReopenRequestPanel } from "./reopen-request-panel"
import type { ReopenRequest } from "@/lib/types"

const approveReopening = vi.fn()
const refuseReopening = vi.fn()
vi.mock("@/lib/expenses", () => ({
  approveReopening: (...args: unknown[]) => approveReopening(...args),
  refuseReopening: (...args: unknown[]) => refuseReopening(...args),
}))

/**
 * Une demande telle que le serveur la rend : `can_decide` y tient compte de
 * l'état, du rôle et de l'auteur, le composant ne recopie aucune de ces
 * règles.
 */
function demande(overrides: Partial<ReopenRequest>): ReopenRequest {
  return {
    id: 5,
    dossier: 14,
    dossier_number: "N-2026-014",
    dossier_label: "Mission commerciale Lomé",
    dossier_status: "submitted",
    country: 2,
    status: "pending",
    status_display: "En attente",
    motif: "Piece a remplacer : la facture jointe correspond a une autre mission.",
    previous_status: "submitted",
    previous_status_display: "Soumis",
    requested_by: "pays.togo",
    decided_by: "",
    decided_at: null,
    decision_note: "",
    can_decide: true,
    created_at: "2026-09-15T10:00:00Z",
    updated_at: "2026-09-15T10:00:00Z",
    ...overrides,
  } as ReopenRequest
}

describe("ReopenRequestPanel", () => {
  it("ne s'affiche pas sans demande", () => {
    const { container } = render(<ReopenRequestPanel rows={[]} onDecided={vi.fn()} />)

    expect(container).toBeEmptyDOMElement()
  })

  it("montre l'état contesté, le motif et l'auteur", () => {
    render(<ReopenRequestPanel rows={[demande({})]} onDecided={vi.fn()} />)

    expect(screen.getByText("Dossier soumis à la demande")).toBeInTheDocument()
    expect(screen.getByText(/Piece a remplacer/)).toBeInTheDocument()
    expect(screen.getByText(/pays\.togo/)).toBeInTheDocument()
    expect(screen.getByText("En attente")).toBeInTheDocument()
  })

  it("propose d'approuver ou de refuser quand le serveur ouvre la décision", async () => {
    approveReopening.mockResolvedValue(demande({ status: "approved", can_decide: false }))
    const onDecided = vi.fn().mockResolvedValue(undefined)
    render(<ReopenRequestPanel rows={[demande({})]} onDecided={onDecided} />)

    fireEvent.click(screen.getByRole("button", { name: "Approuver la réouverture" }))

    await waitFor(() => expect(approveReopening).toHaveBeenCalledWith(5))
    await waitFor(() => expect(onDecided).toHaveBeenCalled())
  })

  it("ne propose rien quand le serveur ferme la décision", () => {
    render(<ReopenRequestPanel rows={[demande({ can_decide: false })]} onDecided={vi.fn()} />)

    expect(screen.queryByRole("button", { name: "Approuver la réouverture" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Refuser" })).toBeNull()
  })

  it("exige un motif pour refuser, puis l'envoie", async () => {
    refuseReopening.mockResolvedValue(demande({ status: "refused", can_decide: false }))
    const onDecided = vi.fn().mockResolvedValue(undefined)
    render(<ReopenRequestPanel rows={[demande({})]} onDecided={onDecided} />)

    fireEvent.click(screen.getByRole("button", { name: "Refuser" }))
    const dialogue = screen.getByRole("dialog")
    expect(dialogue).toHaveTextContent("N-2026-014")
    fireEvent.click(screen.getAllByRole("button", { name: "Refuser" }).at(-1)!)
    expect(screen.getByRole("alert")).toHaveTextContent("motiv")
    expect(refuseReopening).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText("Motif du refus"), { target: { value: "La piece est bien celle de la mission." } })
    fireEvent.click(screen.getAllByRole("button", { name: "Refuser" }).at(-1)!)

    await waitFor(() => expect(refuseReopening).toHaveBeenCalledWith(5, "La piece est bien celle de la mission."))
    await waitFor(() => expect(onDecided).toHaveBeenCalled())
  })

  it("affiche la décision et son auteur sur une demande tranchée", () => {
    render(
      <ReopenRequestPanel
        rows={[demande({ status: "refused", status_display: "Refusée", can_decide: false, decided_by: "rh.innov", decision_note: "La piece est correcte." })]}
        onDecided={vi.fn()}
      />,
    )

    expect(screen.getByText("Refusée")).toBeInTheDocument()
    expect(screen.getByText(/Décision : La piece est correcte\./)).toBeInTheDocument()
    expect(screen.getByText(/rh\.innov/)).toBeInTheDocument()
  })
})
