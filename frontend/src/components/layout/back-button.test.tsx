import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { BackButton } from "./back-button"

function Ecran({ dansLeMenu }: { dansLeMenu?: boolean }) {
  const { pathname } = useLocation()
  return (
    <>
      <BackButton dansLeMenu={dansLeMenu} />
      <p data-testid="chemin">{pathname}</p>
    </>
  )
}

function afficher(chemin: string, dansLeMenu?: boolean) {
  return render(
    <MemoryRouter initialEntries={[chemin]}>
      <Routes>
        <Route path="*" element={<Ecran dansLeMenu={dansLeMenu} />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("BackButton", () => {
  it("n'apparaît pas sur l'accueil", () => {
    afficher("/")

    expect(screen.queryByRole("button", { name: "Retour" })).toBeNull()
  })

  it("ramène une fiche ouverte directement à sa liste", () => {
    // Sans historique dans l'application (page ouverte par un lien reçu ou
    // un favori), revenir en arrière sortirait de l'application : le bouton
    // mène à la liste de la section.
    afficher("/dossiers/12")

    fireEvent.click(screen.getByRole("button", { name: "Retour" }))

    expect(screen.getByTestId("chemin")).toHaveTextContent("/dossiers")
  })

  it("ramène une section à l'accueil", () => {
    afficher("/configuration")

    fireEvent.click(screen.getByRole("button", { name: "Retour" }))

    expect(screen.getByTestId("chemin")).toHaveTextContent("/")
  })

  it("cède sa ligne à la barre latérale sur une entrée du menu, dès lg", () => {
    afficher("/registre", true)
    expect(screen.getByRole("button", { name: "Retour" }).parentElement).toHaveClass("lg:hidden")
  })

  it("reste en vue ailleurs", () => {
    afficher("/projets/3")
    expect(screen.getByRole("button", { name: "Retour" }).parentElement).not.toHaveClass("lg:hidden")
  })
})
