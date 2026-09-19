import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { ConfigurationPage } from "./index"

let droits: Record<string, boolean> = {}
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ can: (cle: string) => droits[cle] ?? false, me: {} }),
}))
// Les sections chargent des données ; seul le choix de l'onglet est testé.
vi.mock("./general-section", () => ({ GeneralSection: () => <p>Section générale</p> }))
vi.mock("./users-section", () => ({ UsersSection: () => <p>Section comptes</p> }))
vi.mock("./countries-section", () => ({ CountriesSection: () => <p>Section pays</p> }))
vi.mock("./permissions-section", () => ({ PermissionsSection: () => <p>Section permissions</p> }))
vi.mock("./import-section", () => ({ ImportSection: () => <p>Section import</p> }))

function monter(recherche: string) {
  return render(
    <MemoryRouter initialEntries={[`/configuration${recherche}`]}>
      <ConfigurationPage />
    </MemoryRouter>,
  )
}

/**
 * Régression : l'onglet venait de l'URL sans être validé. `?onglet=xyz`, ou
 * `?onglet=import` sur un compte sans le droit, laissait une barre d'onglets
 * sans onglet actif et aucun contenu — une page blanche sans explication.
 */
describe("Configuration — onglet lu dans l'URL", () => {
  it("retombe sur l'onglet général quand la valeur est inconnue", () => {
    droits = { "data.import": true }

    monter("?onglet=xyz")

    expect(screen.getByText("Section générale")).toBeInTheDocument()
  })

  it("retombe sur l'onglet général quand le compte n'a pas le droit", () => {
    droits = { "data.import": false }

    monter("?onglet=import")

    expect(screen.getByText("Section générale")).toBeInTheDocument()
    expect(screen.queryByText("Section import")).toBeNull()
  })

  it("ouvre l'onglet demandé quand il est valide", () => {
    droits = { "data.import": true }

    monter("?onglet=permissions")

    expect(screen.getByText("Section permissions")).toBeInTheDocument()
  })
})
