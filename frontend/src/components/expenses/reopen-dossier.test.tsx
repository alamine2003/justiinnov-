import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ReopenDossier } from "@/components/expenses/reopen-dossier"
import { ApiError } from "@/lib/api"
import type { DossierDetail, Expense, Permissions, WorkflowStatus } from "@/lib/types"

let droits: Partial<Permissions> = { reopen_dossiers: true }

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    can: (permission: keyof Permissions) => Boolean(droits[permission]),
  }),
}))

function ligne(status: WorkflowStatus): Expense {
  return { id: 1, status, status_display: status } as unknown as Expense
}

function dossier(status: WorkflowStatus, expenses: Expense[] = [ligne("submitted")]): DossierDetail {
  return {
    id: 12,
    number: "N-2026-012",
    status,
    status_display: status,
    expenses,
    proofs: [],
  } as unknown as DossierDetail
}

describe("ReopenDossier — visibilité", () => {
  it("s'affiche au siège sur un dossier soumis", () => {
    droits = { reopen_dossiers: true }
    render(<ReopenDossier dossier={dossier("submitted")} onReopen={vi.fn()} />)

    expect(screen.getByRole("button", { name: "Rouvrir" })).toBeInTheDocument()
  })

  it.each<WorkflowStatus>(["in_review", "unjustified"])("s'affiche aussi depuis « %s »", (status) => {
    droits = { reopen_dossiers: true }
    render(<ReopenDossier dossier={dossier(status)} onReopen={vi.fn()} />)

    expect(screen.getByRole("button", { name: "Rouvrir" })).toBeInTheDocument()
  })

  it("reste absent sans le droit", () => {
    droits = { reopen_dossiers: false }
    render(<ReopenDossier dossier={dossier("submitted")} onReopen={vi.fn()} />)

    expect(screen.queryByRole("button", { name: "Rouvrir" })).toBeNull()
  })

  it.each<WorkflowStatus>(["draft", "justified", "closed"])("reste absent depuis « %s »", (status) => {
    droits = { reopen_dossiers: true }
    render(<ReopenDossier dossier={dossier(status)} onReopen={vi.fn()} />)

    expect(screen.queryByRole("button", { name: "Rouvrir" })).toBeNull()
  })

  it("reste absent quand une ligne est déjà justifiée : le serveur refuserait", () => {
    droits = { reopen_dossiers: true }
    render(
      <ReopenDossier
        dossier={dossier("submitted", [ligne("submitted"), ligne("justified")])}
        onReopen={vi.fn()}
      />,
    )

    expect(screen.queryByRole("button", { name: "Rouvrir" })).toBeNull()
  })
})

describe("ReopenDossier — dialogue", () => {
  it("exige un motif sans appeler le serveur", () => {
    droits = { reopen_dossiers: true }
    const onReopen = vi.fn()
    render(<ReopenDossier dossier={dossier("submitted")} onReopen={onReopen} />)

    fireEvent.click(screen.getByRole("button", { name: "Rouvrir" }))
    const dialogue = screen.getByRole("dialog")
    expect(dialogue).toHaveTextContent("Rouvrir le dossier N-2026-012")
    fireEvent.click(screen.getAllByRole("button", { name: "Rouvrir" }).at(-1)!)

    expect(screen.getByRole("alert")).toHaveTextContent("motiv")
    expect(onReopen).not.toHaveBeenCalled()
  })

  it("transmet le motif et se referme", async () => {
    droits = { reopen_dossiers: true }
    const onReopen = vi.fn().mockResolvedValue(undefined)
    render(<ReopenDossier dossier={dossier("submitted")} onReopen={onReopen} />)

    fireEvent.click(screen.getByRole("button", { name: "Rouvrir" }))
    fireEvent.change(screen.getByLabelText("Motif"), {
      target: { value: "  Facture du 3 mars illisible  " },
    })
    fireEvent.click(screen.getAllByRole("button", { name: "Rouvrir" }).at(-1)!)

    await waitFor(() => expect(onReopen).toHaveBeenCalledWith("Facture du 3 mars illisible"))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("affiche les refus du serveur par champ et reste ouvert", async () => {
    droits = { reopen_dossiers: true }
    const onReopen = vi.fn().mockRejectedValue(
      new ApiError(400, "expenses : Ligne 4 justifiee.", {
        expenses: ["Ligne 4 justifiee."],
        status: ["Statut incompatible."],
      }),
    )
    render(<ReopenDossier dossier={dossier("submitted")} onReopen={onReopen} />)

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
    droits = { reopen_dossiers: true }
    const onReopen = vi.fn().mockRejectedValue(
      new ApiError(400, "Motif : trop court.", { note: ["Trop court."] }),
    )
    render(<ReopenDossier dossier={dossier("submitted")} onReopen={onReopen} />)

    fireEvent.click(screen.getByRole("button", { name: "Rouvrir" }))
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "x" } })
    fireEvent.click(screen.getAllByRole("button", { name: "Rouvrir" }).at(-1)!)

    expect(await screen.findByRole("alert")).toHaveTextContent("Trop court.")
    expect(screen.getByLabelText("Motif")).toHaveAttribute("aria-invalid", "true")
  })
})
