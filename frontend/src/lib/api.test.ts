import { describe, expect, it } from "vitest"

import { ApiError, readErrorMessage } from "./api"

describe("readErrorMessage", () => {
  it("retient le champ detail de DRF", () => {
    expect(readErrorMessage({ detail: "Non autorisé." })).toBe("Non autorisé.")
  })

  it("remonte les erreurs de validation, sans quoi l'utilisateur verrait « Request failed with status code 400 »", () => {
    expect(
      readErrorMessage({ non_field_errors: ["Une enveloppe existe déjà."] }),
    ).toBe("Une enveloppe existe déjà.")
  })

  it("assemble plusieurs erreurs de champs", () => {
    const message = readErrorMessage({
      amount: ["Montant invalide."],
      note: ["Un refus doit être motivé."],
    })
    expect(message).toContain("Montant invalide.")
    expect(message).toContain("Un refus doit être motivé.")
  })

  it("accepte une réponse en texte brut", () => {
    expect(readErrorMessage("Erreur serveur")).toBe("Erreur serveur")
  })

  it("renvoie null quand rien n'est exploitable", () => {
    expect(readErrorMessage(null)).toBeNull()
    expect(readErrorMessage({})).toBeNull()
  })
})

describe("ApiError", () => {
  it("conserve le code HTTP pour que l'appelant puisse le distinguer", () => {
    const error = new ApiError(403, "Interdit")
    expect(error.status).toBe(403)
    expect(error).toBeInstanceOf(Error)
  })
})
