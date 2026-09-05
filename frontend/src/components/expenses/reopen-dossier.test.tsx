import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ReopenDossier } from "@/components/expenses/reopen-dossier"
import { ApiError } from "@/lib/api"
import type { DossierDetail } from "@/lib/types"

/**
 * Le serveur dit s'il accepterait la réouverture (`allowed_actions`) : droit,
 * état du dossier, lignes déjà justifiées. Le composant ne lit rien d'autre.
 */
function dossier(allowedActions: DossierDetail["allowed_actions"]): DossierDetail {
  return {
    id: 12,
    number: "N-2026-012",
    status: "submitted",
    status_display: "Soumis",
    allowed_actions: allowedActions,
    expenses: [],
    proofs: [],
  } as unknown as DossierDetail
}

describe("ReopenDossier — visibilité", () => {
  it("s'affiche quand le serveur ouvre la réouverture", () => {
    render(<ReopenDossier dossier={dossier(["reopen", "review"])} onReopen={vi.fn()} />)

    expect(screen.getByRole("button", { name: "Rouvrir" })).toBeInTheDocument()
  })

  it("reste absent quand le serveur ne l'ouvre pas", () => {
    render(<ReopenDossier dossier={dossier(["review", "reject"])} onReopen={vi.fn()} />)

    expect(screen.queryByRole("button", { name: "Rouvrir" })).toBeNull()
  })

  it("reste absent quand le serveur n'ouvre rien", () => {
    render(<ReopenDossier dossier={dossier([])} onReopen={vi.fn()} />)

    expect(screen.queryByRole("button", { name: "Rouvrir" })).toBeNull()
  })
})

describe("ReopenDossier — dialogue", () => {
  it("exige un motif sans appeler le serveur", () => {
    const onReopen = vi.fn()
    render(<ReopenDossier dossier={dossier(["reopen"])} onReopen={onReopen} />)

    fireEvent.click(screen.getByRole("button", { name: "Rouvrir" }))
    const dialogue = screen.getByRole("dialog")
    expect(dialogue).toHaveTextContent("Rouvrir le dossier N-2026-012")
    fireEvent.click(screen.getAllByRole("button", { name: "Rouvrir" }).at(-1)!)

    expect(screen.getByRole("alert")).toHaveTextContent("motiv")
    expect(onReopen).not.toHaveBeenCalled()
  })

  it("transmet le motif et se referme", async () => {
    const onReopen = vi.fn().mockResolvedValue(undefined)
    render(<ReopenDossier dossier={dossier(["reopen"])} onReopen={onReopen} />)

    fireEvent.click(screen.getByRole("button", { name: "Rouvrir" }))
    fireEvent.change(screen.getByLabelText("Motif"), {
      target: { value: "  Facture du 3 mars illisible  " },
    })
    fireEvent.click(screen.getAllByRole("button", { name: "Rouvrir" }).at(-1)!)

    await waitFor(() => expect(onReopen).toHaveBeenCalledWith("Facture du 3 mars illisible"))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("affiche les refus du serveur par champ et reste ouvert", async () => {
    const onReopen = vi.fn().mockRejectedValue(
      new ApiError(400, "expenses : Ligne 4 justifiee.", {
        expenses: ["Ligne 4 justifiee."],
        status: ["Statut incompatible."],
      }),
    )
    render(<ReopenDossier dossier={dossier(["reopen"])} onReopen={onReopen} />)

    fireEvent.click(screen.getByRole("button", { name: "Rouvrir" }))
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "Motif" } })
    fireEvent.click(screen.getAllByRole("button", { name: "Rouvrir" }).at(-1)!)

    const alerte = await screen.findByRole("alert")
    expect(alerte).toHaveTextContent("Ligne 4 justifiee.")
    expect(alerte).toHaveTextContent("Statut incompatible.")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByLabelText("Motif")).toHaveValue("Motif")
  })

  it("rattache un refus du motif au champ", async () => {
    const onReopen = vi.fn().mockRejectedValue(
      new ApiError(400, "Motif : trop court.", { note: ["Trop court."] }),
    )
    render(<ReopenDossier dossier={dossier(["reopen"])} onReopen={onReopen} />)

    fireEvent.click(screen.getByRole("button", { name: "Rouvrir" }))
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "x" } })
    fireEvent.click(screen.getAllByRole("button", { name: "Rouvrir" }).at(-1)!)

    expect(await screen.findByRole("alert")).toHaveTextContent("Trop court.")
    expect(screen.getByLabelText("Motif")).toHaveAttribute("aria-invalid", "true")
  })
})
