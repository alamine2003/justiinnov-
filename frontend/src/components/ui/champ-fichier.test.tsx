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

  it("se désactive comme un champ natif, et s'affiche comme un <Input> désactivé", () => {
    render(<ChampFichier aria-label="Pièce" disabled />)
    const champ = screen.getByLabelText("Pièce")
    expect(champ).toBeDisabled()
    expect(champ.parentElement).toHaveClass("has-[input:disabled]:opacity-50", "has-[input:disabled]:bg-input/50")
  })

  it("se décrit par le fichier choisi, dans la langue de l'interface, et non par la valeur native", () => {
    // Le texte visible était `aria-hidden` : un lecteur d'écran annonçait
    // « No file chosen » sous une interface en français.
    render(
      <>
        <Label htmlFor="piece">Fichier</Label>
        <ChampFichier id="piece" aria-describedby="aide" />
        <p id="aide">PDF, JPEG ou PNG.</p>
      </>,
    )

    const champ = screen.getByLabelText("Fichier")
    expect(champ).toHaveAccessibleDescription("Aucun fichier choisi PDF, JPEG ou PNG.")
    // Le nom reste l'étiquette seule : le texte de l'état, dans l'étiquette
    // qui enveloppe le champ, ne s'y ajoute pas (il serait annoncé deux fois).
    expect(champ).toHaveAccessibleName("Fichier")
    expect(champ).toHaveAttribute("title", "Aucun fichier choisi")

    const long = "facture-hotel-congres-de-cardiologie-abidjan-2026-chambre-double-trois-nuits-recu.pdf"
    fireEvent.change(champ, { target: { files: [new File(["%PDF-1.4"], long, { type: "application/pdf" })] } })

    expect(champ).toHaveAccessibleDescription(`${long} PDF, JPEG ou PNG.`)
    expect(champ).toHaveAccessibleName("Fichier")
    // Tronqué à l'écran, le nom se lit en entier au survol : le champ natif,
    // posé sur tout le reste, porte l'infobulle.
    expect(champ).toHaveAttribute("title", long)
    expect(screen.getByText(long)).toHaveAttribute("title", long)
  })

  it("s'affiche invalide comme un <Input> quand le champ l'est", () => {
    render(<ChampFichier aria-label="Pièce" aria-invalid />)

    const champ = screen.getByLabelText("Pièce")
    expect(champ).toHaveAttribute("aria-invalid", "true")
    // La bordure et l'anneau destructifs d'<Input>, portés par le cadre.
    expect(champ.parentElement).toHaveClass(
      "has-[input[aria-invalid=true]]:border-destructive",
      "has-[input[aria-invalid=true]]:ring-destructive/20",
    )
  })
})
