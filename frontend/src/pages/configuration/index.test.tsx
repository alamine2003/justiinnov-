import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { ConfigurationPage } from "./index"

// Les sections chargent des données ; seul le choix de l'onglet est testé.
vi.mock("./general-section", () => ({ GeneralSection: () => <p>Section générale</p> }))
vi.mock("./users-section", () => ({ UsersSection: () => <p>Section comptes</p> }))
vi.mock("./countries-section", () => ({ CountriesSection: () => <p>Section pays</p> }))
vi.mock("./permissions-section", () => ({ PermissionsSection: () => <p>Section permissions</p> }))

function monter(recherche: string) {
  return render(
    <MemoryRouter initialEntries={[`/configuration${recherche}`]}>
      <ConfigurationPage />
    </MemoryRouter>,
  )
}

/**
 * Régression : l'onglet venait de l'URL sans être validé. `?onglet=xyz`, ou
 * l'ancien `?onglet=import`, laissait une barre d'onglets sans onglet actif
 * et aucun contenu — une page blanche sans explication.
 */
describe("Configuration — onglet lu dans l'URL", () => {
  it("retombe sur l'onglet général quand la valeur est inconnue", () => {
    monter("?onglet=xyz")

    expect(screen.getByText("Section générale")).toBeInTheDocument()
  })

  it("n'a plus d'onglet d'import : l'import vit avec les dossiers", () => {
    // Importer, c'est déclarer (décision 89) : un ancien lien retombe sur
    // l'onglet général, sans onglet d'import.
    monter("?onglet=import")

    expect(screen.getByText("Section générale")).toBeInTheDocument()
    expect(screen.queryByRole("tab", { name: "Import" })).toBeNull()
  })

  it("ouvre l'onglet demandé quand il est valide", () => {
    monter("?onglet=permissions")

    expect(screen.getByText("Section permissions")).toBeInTheDocument()
  })
})
