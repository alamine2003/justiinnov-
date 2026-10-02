import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { RenameDossier } from "./rename-dossier"
import { ApiError } from "@/lib/api"
import type { DossierDetail } from "@/lib/types"

function dossier(actions: string[]): DossierDetail {
  return {
    number: "TG-P-2026-001-D001",
    label: "Stands",
    allowed_actions: actions,
  } as unknown as DossierDetail
}

describe("RenameDossier", () => {
  it("ne s'affiche que si le serveur propose « rename »", () => {
    render(<RenameDossier dossier={dossier(["edit"])} onRename={vi.fn()} />)
    expect(screen.queryByRole("button", { name: "Renommer" })).toBeNull()
  })

  it("part du titre actuel et envoie le nouveau, sans espaces autour", async () => {
    const onRename = vi.fn().mockResolvedValue(undefined)
    render(<RenameDossier dossier={dossier(["rename"])} onRename={onRename} />)

    fireEvent.click(screen.getByRole("button", { name: "Renommer" }))
    const champ = await screen.findByLabelText("Libellé")
    expect(champ).toHaveValue("Stands")
    fireEvent.change(champ, { target: { value: "  Stands du hall A " } })
    fireEvent.click(screen.getAllByRole("button", { name: "Renommer" }).at(-1)!)

    await vi.waitFor(() => expect(onRename).toHaveBeenCalledWith("Stands du hall A"))
  })

  it("refuse un titre vide sans appeler le serveur", async () => {
    const onRename = vi.fn()
    render(<RenameDossier dossier={dossier(["rename"])} onRename={onRename} />)

    fireEvent.click(screen.getByRole("button", { name: "Renommer" }))
    fireEvent.change(await screen.findByLabelText("Libellé"), { target: { value: "   " } })
    fireEvent.click(screen.getAllByRole("button", { name: "Renommer" }).at(-1)!)

    expect(await screen.findByRole("alert")).toHaveTextContent("Indiquez le nouveau titre.")
    expect(onRename).not.toHaveBeenCalled()
  })

  it("affiche le refus du serveur sans fermer le dialogue", async () => {
    const onRename = vi
      .fn()
      .mockRejectedValue(new ApiError(400, "Refus", { label: ["Titre trop long."] }))
    render(<RenameDossier dossier={dossier(["rename"])} onRename={onRename} />)

    fireEvent.click(screen.getByRole("button", { name: "Renommer" }))
    fireEvent.click((await screen.findAllByRole("button", { name: "Renommer" })).at(-1)!)

    expect(await screen.findByRole("alert")).toHaveTextContent("Titre trop long.")
    expect(screen.getByLabelText("Libellé")).toHaveValue("Stands")
  })
})
