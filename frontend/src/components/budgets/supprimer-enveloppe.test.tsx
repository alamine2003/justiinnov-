import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { SupprimerEnveloppe } from "./supprimer-enveloppe"
import { ApiError } from "@/lib/api"
import type { Budget } from "@/lib/types"

/** Une enveloppe telle que le serveur la rend : `can_delete` y dit tout. */
function enveloppe(can_delete: boolean): Budget {
  return { id: 7, year: 2027, can_delete } as unknown as Budget
}

describe("SupprimerEnveloppe", () => {
  it("n'existe pas quand le serveur refuserait la suppression", () => {
    render(<SupprimerEnveloppe budget={enveloppe(false)} nom="Togo" onDelete={vi.fn()} />)

    expect(screen.queryByRole("button")).toBeNull()
  })

  it("demande confirmation, puis supprime", async () => {
    const onDelete = vi.fn().mockResolvedValue(undefined)
    render(<SupprimerEnveloppe budget={enveloppe(true)} nom="Togo" onDelete={onDelete} />)

    fireEvent.click(screen.getByRole("button", { name: "Supprimer l'enveloppe Togo" }))
    expect(onDelete).not.toHaveBeenCalled()
    expect(screen.getByRole("dialog")).toHaveTextContent("Supprimer « Togo » (2027) ?")

    fireEvent.click(screen.getByRole("button", { name: "Supprimer" }))

    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ id: 7 })))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("garde le dialogue ouvert et dit pourquoi le serveur a refusé", async () => {
    const onDelete = vi.fn().mockRejectedValue(
      new ApiError(400, "Refus", {
        budget: ["Des dépenses sont imputées sur cette enveloppe : elle se désactive, elle ne se supprime pas."],
      }),
    )
    render(<SupprimerEnveloppe budget={enveloppe(true)} nom="Togo" onDelete={onDelete} />)

    fireEvent.click(screen.getByRole("button", { name: "Supprimer l'enveloppe Togo" }))
    fireEvent.click(screen.getByRole("button", { name: "Supprimer" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Des dépenses sont imputées")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })
})
