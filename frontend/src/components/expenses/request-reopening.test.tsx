import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { RequestReopening } from "@/components/expenses/request-reopening"
import { ApiError } from "@/lib/api"
import type { DossierDetail } from "@/lib/types"

/**
 * Le serveur dit s'il accepterait la demande (`allowed_actions`) : droit,
 * dossier soumis ou en contrôle, aucune ligne constatée, aucune demande
 * déjà en attente. Le composant ne lit rien d'autre.
 */
function dossier(allowedActions: string[]): DossierDetail {
  return {
    id: 14,
    number: "N-2026-014",
    status: "submitted",
    status_display: "Soumis",
    allowed_actions: allowedActions,
  } as unknown as DossierDetail
}

describe("RequestReopening — visibilité", () => {
  it("s'affiche quand le serveur ouvre la demande", () => {
    render(<RequestReopening dossier={dossier(["request_reopening"])} onRequest={vi.fn()} />)

    expect(screen.getByRole("button", { name: "Demander la réouverture" })).toBeInTheDocument()
  })

  it("reste absent quand le serveur ne l'ouvre pas", () => {
    render(<RequestReopening dossier={dossier(["review"])} onRequest={vi.fn()} />)

    expect(screen.queryByRole("button", { name: "Demander la réouverture" })).toBeNull()
  })
})

describe("RequestReopening — dialogue", () => {
  it("exige un motif sans appeler le serveur", () => {
    const onRequest = vi.fn()
    render(<RequestReopening dossier={dossier(["request_reopening"])} onRequest={onRequest} />)

    fireEvent.click(screen.getByRole("button", { name: "Demander la réouverture" }))
    expect(screen.getByRole("dialog")).toHaveTextContent("N-2026-014")
    fireEvent.click(screen.getByRole("button", { name: "Demander" }))

    expect(screen.getByRole("alert")).toHaveTextContent("motiv")
    expect(onRequest).not.toHaveBeenCalled()
  })

  it("transmet le motif et se referme", async () => {
    const onRequest = vi.fn().mockResolvedValue(undefined)
    render(<RequestReopening dossier={dossier(["request_reopening"])} onRequest={onRequest} />)

    fireEvent.click(screen.getByRole("button", { name: "Demander la réouverture" }))
    fireEvent.change(screen.getByLabelText("Motif"), {
      target: { value: "  Piece a remplacer  " },
    })
    fireEvent.click(screen.getByRole("button", { name: "Demander" }))

    await waitFor(() => expect(onRequest).toHaveBeenCalledWith("Piece a remplacer"))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("affiche un refus du serveur sur le dossier et reste ouvert", async () => {
    const onRequest = vi.fn().mockRejectedValue(
      new ApiError(400, "Une ligne est deja constatee.", {
        expenses: ["Une ligne est deja constatee."],
      }),
    )
    render(<RequestReopening dossier={dossier(["request_reopening"])} onRequest={onRequest} />)

    fireEvent.click(screen.getByRole("button", { name: "Demander la réouverture" }))
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "Motif" } })
    fireEvent.click(screen.getByRole("button", { name: "Demander" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Une ligne est deja constatee.")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByLabelText("Motif")).toHaveValue("Motif")
  })
})
