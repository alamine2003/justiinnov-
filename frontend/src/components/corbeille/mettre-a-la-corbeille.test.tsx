import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api"
import { MettreALaCorbeille } from "./mettre-a-la-corbeille"

const { mettreALaCorbeille } = vi.hoisted(() => ({ mettreALaCorbeille: vi.fn() }))
vi.mock("@/lib/corbeille", () => ({ mettreALaCorbeille }))

const resultat = { element: { id: 1 }, emportes: { projet: 0, dossier: 1, ligne: 2, piece: 1 } }

function monter(onDone = vi.fn()) {
  render(<MettreALaCorbeille nature="dossier" id={7} libelle="TG-P-2026-001-D001" onDone={onDone} />)
  fireEvent.click(screen.getByRole("button", { name: "Mettre à la corbeille" }))
  return onDone
}

// Entre accolades : une fonction rendue par `beforeEach` serait appelée
// après le test, comme un nettoyage — et `mockReset` rend le mock.
beforeEach(() => {
  mettreALaCorbeille.mockReset()
})

describe("MettreALaCorbeille (décision 120)", () => {
  it("dit ce qui part avec l'objet et que la corbeille ne se vide pas", () => {
    monter()

    expect(screen.getByText("Le dossier part avec ses lignes et leurs justificatifs.")).toBeInTheDocument()
    expect(screen.getByText(/elle ne se vide pas et ne remet rien en place/)).toBeInTheDocument()
  })

  it("exige un motif avant d'appeler le serveur", async () => {
    monter()

    fireEvent.click(screen.getAllByRole("button", { name: "Mettre à la corbeille" }).at(-1)!)

    expect(await screen.findByText(/Indiquez le motif/)).toBeInTheDocument()
    expect(mettreALaCorbeille).not.toHaveBeenCalled()
  })

  it("envoie la nature, l'objet et le motif, puis prévient l'écran", async () => {
    mettreALaCorbeille.mockResolvedValue(resultat)
    const onDone = monter()

    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: " Saisie d'essai " } })
    fireEvent.click(screen.getAllByRole("button", { name: "Mettre à la corbeille" }).at(-1)!)

    await waitFor(() => expect(onDone).toHaveBeenCalledWith(resultat))
    expect(mettreALaCorbeille).toHaveBeenCalledWith("dossier", 7, "Saisie d'essai")
  })

  it("garde le dialogue ouvert et lit le refus du serveur", async () => {
    mettreALaCorbeille.mockRejectedValue(
      new ApiError(400, "Requête invalide", { nature: ["Les suppressions sont fermées."] }),
    )
    const onDone = monter()

    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "Essai" } })
    fireEvent.click(screen.getAllByRole("button", { name: "Mettre à la corbeille" }).at(-1)!)

    expect(await screen.findByText("Les suppressions sont fermées.")).toBeInTheDocument()
    expect(onDone).not.toHaveBeenCalled()
  })
})
