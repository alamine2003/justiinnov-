import { describe, expect, it } from "vitest"

import { exigerUneCibleJetable } from "./cible.ts"

describe("exigerUneCibleJetable (SHOT_BASE, GUIDES_CIBLE_JETABLE)", () => {
  it.each([
    "http://localhost:5173",
    "http://localhost",
    "https://localhost:5173/",
    "http://LOCALHOST:5173",
    "http://127.0.0.1:5173",
    "http://[::1]:5173",
  ])("accepte la machine locale sans levée (%s)", (base) => {
    expect(exigerUneCibleJetable(base, undefined)).toBe(base)
  })

  // SHOT_BASE n'était jamais contrôlée : un domaine de production
  // recevait un projet, un dossier soumis et une pièce qui ne se suppriment pas.
  it.each([
    "https://justi.innovpharma.net",
    "https://preprod.justi.innovpharma.net:443",
    "http://192.168.1.20:5173",
    "http://127.0.0.2:5173",
    "http://localhost.innovpharma.net",
    // L'hôte est après l'arobase : « localhost » n'y est qu'un identifiant.
    "http://localhost@justi.innovpharma.net",
  ])("refuse un autre hôte sans levée (%s)", (base) => {
    expect(() => exigerUneCibleJetable(base, undefined)).toThrow("GUIDES_CIBLE_JETABLE=oui")
  })

  it("nomme l'hôte refusé et ce qui est accepté", () => {
    expect(() => exigerUneCibleJetable("https://justi.innovpharma.net", undefined)).toThrow(
      "SHOT_BASE vise justi.innovpharma.net, qui n'est ni localhost, ni 127.0.0.1, ni [::1].",
    )
  })

  it.each(["oui", " oui "])("accepte un autre hôte sur levée explicite (%j)", (levee) => {
    expect(exigerUneCibleJetable("https://recette.exemple.test", levee)).toBe("https://recette.exemple.test")
  })

  it.each(["", "1", "true", "OUI", "non"])("refuse une levée approchante (%j)", (levee) => {
    expect(() => exigerUneCibleJetable("https://justi.innovpharma.net", levee)).toThrow(
      "Relancez avec GUIDES_CIBLE_JETABLE=oui",
    )
  })

  it("dit que la valeur de levée donnée ne suffit pas", () => {
    expect(() => exigerUneCibleJetable("https://justi.innovpharma.net", "1")).toThrow(
      "seule la valeur « oui » lève le garde-fou",
    )
  })

  it.each(["", "exemple.invalid", "http://"])("refuse une adresse illisible (%j)", (base) => {
    expect(() => exigerUneCibleJetable(base, "oui")).toThrow("SHOT_BASE n'est pas une adresse lisible")
  })

  // « localhost:5173 » sans schéma se lit comme le protocole « localhost: ».
  it.each(["file:///tmp/guides", "localhost:5173"])("refuse un autre protocole que http ou https, même levé (%s)", (base) => {
    expect(() => exigerUneCibleJetable(base, "oui")).toThrow("adresse http ou https")
  })
})
