import { describe, expect, it } from "vitest"
import { parentPath } from "./navigation"

describe("parentPath — la liste de la section", () => {
  it("remonte d'une fiche à sa liste", () => {
    expect(parentPath("/dossiers/12")).toBe("/dossiers")
    expect(parentPath("/countries/3")).toBe("/countries")
  })

  it("remonte d'une section à l'accueil", () => {
    expect(parentPath("/dossiers")).toBe("/")
    expect(parentPath("/configuration")).toBe("/")
    expect(parentPath("/")).toBe("/")
  })
})
