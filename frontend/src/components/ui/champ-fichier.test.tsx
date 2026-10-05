import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ChampFichier } from "./champ-fichier"
import { Label } from "./label"

/**
 * Le champ natif écrivait « Choose File » dans une interface en français
 * (et l'inverse) : il suit la langue du navigateur. Le texte vient
 * maintenant du dictionnaire ; le champ natif reste le contrôle.
 */
describe("ChampFichier", () => {
  it("parle la langue de l'interface, et dit le fichier choisi", () => {
    const onChange = vi.fn()
    render(
      <>
        <Label htmlFor="piece">Fichier</Label>
        <ChampFichier id="piece" accept=".pdf" required onChange={onChange} />
      </>,
    )

    expect(screen.getByText("Choisir un fichier")).toBeInTheDocument()
    expect(screen.getByText("Aucun fichier choisi")).toBeInTheDocument()

    const champ = screen.getByLabelText("Fichier")
    expect(champ).toHaveAttribute("type", "file")
    expect(champ).toHaveAttribute("accept", ".pdf")
    expect(champ).toBeRequired()

    const fichier = new File(["%PDF-1.4"], "recu-0142.pdf", { type: "application/pdf" })
    fireEvent.change(champ, { target: { files: [fichier] } })

    expect(screen.getByText("recu-0142.pdf")).toBeInTheDocument()
    expect(screen.queryByText("Aucun fichier choisi")).toBeNull()
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it("couvre tout le champ : un fichier glissé y tombe, pas dans l'onglet", () => {
    // Masqué en `sr-only`, le champ natif ne faisait plus qu'un pixel : un
    // fichier lâché sur le champ visible ouvrait le PDF à la place de la page.
    render(<ChampFichier aria-label="Pièce" />)

    const champ = screen.getByLabelText("Pièce")
    expect(champ).not.toHaveClass("sr-only")
    expect(champ).toHaveClass("absolute", "inset-0", "opacity-0")
    expect(champ.parentElement).toHaveClass("relative")
  })

  it("se désactive comme un champ natif", () => {
    render(<ChampFichier aria-label="Pièce" disabled />)
    expect(screen.getByLabelText("Pièce")).toBeDisabled()
  })
})
