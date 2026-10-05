import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n"
import { GuidePage } from "."

let droits = new Set<string>()
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ can: (cle: string) => droits.has(cle) }),
}))

const MANAGER = ["projets.create", "expenses.create", "proofs.upload", "dossiers.submit", "data.import"]

function Adresse() {
  const location = useLocation()
  return <output aria-label="adresse">{location.search}</output>
}

function monter(chemin = "/guide") {
  return render(
    <MemoryRouter initialEntries={[chemin]}>
      <Routes>
        <Route path="/guide" element={<><GuidePage /><Adresse /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

const source = (conteneur: HTMLElement) => conteneur.querySelector("video source")?.getAttribute("src")

beforeEach(() => {
  droits = new Set(MANAGER)
})
afterEach(async () => {
  await i18n.changeLanguage("fr")
})

/** Décision 118 : un guide par geste, dans la langue de l'interface, à qui a la capacité. */
describe("GuidePage", () => {
  it("liste les guides du manager dans l'ordre et ouvre le premier, sous-titré", () => {
    const { container } = monter()

    const sommaire = screen.getByRole("navigation", { name: "Les guides" })
    expect(Array.from(sommaire.querySelectorAll("button")).map((b) => b.getAttribute("aria-label"))).toEqual([
      "1. Ouvrir un projet",
      "2. Saisir une dépense",
      "3. Joindre une pièce",
      "4. Soumettre un dossier",
      "5. Importer un classeur",
    ])
    expect(screen.getByRole("button", { name: "1. Ouvrir un projet" })).toHaveAttribute("aria-current", "true")
    expect(source(container)).toBe("/guides/fr/ouvrir-un-projet.webm")
    const piste = container.querySelector("video track")
    expect(piste).toHaveAttribute("src", "/guides/fr/ouvrir-un-projet.vtt")
    expect(piste).toHaveAttribute("srclang", "fr")
    expect(piste).toHaveAttribute("default")
  })

  it("change de vidéo au choix d'un guide, et le garde dans l'adresse", () => {
    const { container } = monter()

    fireEvent.click(screen.getByRole("button", { name: "3. Joindre une pièce" }))

    expect(source(container)).toBe("/guides/fr/joindre-une-piece.webm")
    expect(screen.getByRole("heading", { name: "Joindre une pièce" })).toBeInTheDocument()
    expect(screen.getByLabelText("adresse")).toHaveTextContent("?video=joindre-une-piece")
  })

  it("rouvre le guide de l'adresse, et le premier si l'adresse en nomme un inconnu", () => {
    const { container, unmount } = monter("/guide?video=importer-un-classeur")
    expect(source(container)).toBe("/guides/fr/importer-un-classeur.webm")
    unmount()

    const autre = monter("/guide?video=inconnu")
    expect(source(autre.container)).toBe("/guides/fr/ouvrir-un-projet.webm")
  })

  it("ne montre pas le guide d'un geste fermé au compte", () => {
    droits = new Set(["expenses.create"])

    monter()

    expect(screen.getByRole("button", { name: "1. Saisir une dépense" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Importer un classeur/ })).toBeNull()
  })

  it("suit la langue de l'interface : vidéo, sous-titres et titres en anglais", async () => {
    await i18n.changeLanguage("en")

    const { container } = monter()

    expect(source(container)).toBe("/guides/en/ouvrir-un-projet.webm")
    expect(container.querySelector("video track")).toHaveAttribute("srclang", "en")
    expect(container.querySelector("video")).toHaveAttribute("poster", "/guides/en/ouvrir-un-projet.jpg")
    expect(screen.getByRole("heading", { name: "Open a project" })).toBeInTheDocument()
  })

  it("nomme la vidéo par le titre du guide ouvert", () => {
    const { container } = monter()

    const video = container.querySelector("video")!
    expect(document.getElementById(video.getAttribute("aria-labelledby")!)).toHaveTextContent("Ouvrir un projet")
  })

  it("dit à un compte sans guide pourquoi la page est vide", () => {
    droits = new Set(["audit.read"])

    const { container } = monter()

    expect(screen.getByText("Aucun guide pour votre compte")).toBeInTheDocument()
    expect(container.querySelector("video")).toBeNull()
  })
})
