import { afterEach, describe, expect, it, vi } from "vitest"
import axios, { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios"

import {
  ApiError,
  api,
  apiGet,
  onPasswordChangeRequired,
  onUnauthorized,
  readErrorMessage,
  readFieldErrors,
  setApiLanguage,
  setToken,
} from "./api"

describe("readErrorMessage", () => {
  it("retient le champ detail de DRF", () => {
    expect(readErrorMessage({ detail: "Non autorisé." })).toBe("Non autorisé.")
  })

  it("remonte les erreurs de validation, sans quoi l'utilisateur verrait « Request failed with status code 400 »", () => {
    expect(
      readErrorMessage({ non_field_errors: ["Une enveloppe existe déjà."] }),
    ).toBe("Une enveloppe existe déjà.")
  })

  it("assemble plusieurs erreurs de champs en les nommant", () => {
    const message = readErrorMessage({
      amount: ["Montant invalide."],
      note: ["Un refus doit être motivé."],
    })
    expect(message).toContain("Montant : Montant invalide.")
    expect(message).toContain("Motif : Un refus doit être motivé.")
  })

  it("accepte une réponse en texte brut", () => {
    expect(readErrorMessage("Erreur serveur")).toBe("Erreur serveur")
  })

  it("ignore une page HTML au lieu de la déverser dans l'interface", () => {
    // Une 404 hors des routes de l'API renvoie la page d'erreur Django.
    expect(
      readErrorMessage("<!DOCTYPE html><html><body>Page not found</body></html>"),
    ).toBeNull()
    expect(readErrorMessage("   ")).toBeNull()
  })

  it("renvoie null quand rien n'est exploitable", () => {
    expect(readErrorMessage(null)).toBeNull()
    expect(readErrorMessage({})).toBeNull()
  })
})

describe("readFieldErrors", () => {
  it("aplatit les erreurs imbriquées avec leur chemin", () => {
    expect(
      readFieldErrors({
        amount: ["Montant invalide."],
        figures: { remaining: ["Insuffisant."] },
        lignes: [{}, { title: ["Obligatoire."] }],
      }),
    ).toEqual({
      amount: ["Montant invalide."],
      "figures.remaining": ["Insuffisant."],
      "lignes.1.title": ["Obligatoire."],
    })
  })

  it("ne renvoie rien pour une réponse qui n'est pas un objet", () => {
    expect(readFieldErrors("texte")).toEqual({})
    expect(readFieldErrors(null)).toEqual({})
  })
})

describe("ApiError", () => {
  it("conserve le code HTTP pour que l'appelant puisse le distinguer", () => {
    const error = new ApiError(403, "Interdit")
    expect(error.status).toBe(403)
    expect(error.fields).toEqual({})
    expect(error).toBeInstanceOf(Error)
  })
})

/**
 * Remplace l'adaptateur HTTP d'axios par une réponse fixe : le test exerce
 * l'intercepteur sans réseau ni serveur.
 */
function repondre(status: number, data: unknown) {
  const adapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
    const response = { status, statusText: "", headers: {}, config, data }
    if (status >= 400) {
      throw new AxiosError("Request failed", "ERR_BAD_REQUEST", config, {}, response)
    }
    return response
  }
  api.defaults.adapter = adapter
}

function couperLeReseau() {
  api.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    throw new AxiosError("Network Error", AxiosError.ERR_NETWORK, config)
  }
}

describe("intercepteur de réponse", () => {
  const adaptateurInitial = axios.defaults.adapter

  afterEach(() => {
    api.defaults.adapter = adaptateurInitial
    localStorage.clear()
  })

  it("expose la carte des champs en erreur", async () => {
    repondre(400, { amount: ["Montant invalide."] })

    await expect(api.post("/expenses/", {})).rejects.toMatchObject({
      status: 400,
      fields: { amount: ["Montant invalide."] },
      message: "Montant : Montant invalide.",
    })
  })

  it("prévient les abonnés et efface le jeton sur un 401", async () => {
    setToken("périmé")
    const listener = vi.fn()
    const off = onUnauthorized(listener)
    repondre(401, { detail: "Jeton invalide." })

    await expect(apiGet("/me/")).rejects.toBeInstanceOf(ApiError)

    expect(listener).toHaveBeenCalledOnce()
    expect(localStorage.getItem("justi_token")).toBeNull()
    off()
  })

  it("signale un refus pour mot de passe provisoire", async () => {
    const listener = vi.fn()
    const off = onPasswordChangeRequired(listener)
    repondre(403, {
      detail: "Remplacez votre mot de passe.",
      must_change_password: true,
    })

    await expect(apiGet("/dossiers/")).rejects.toMatchObject({ status: 403 })

    expect(listener).toHaveBeenCalledOnce()
    off()
  })

  it("dit que le serveur est injoignable plutôt que « Network Error »", async () => {
    couperLeReseau()

    await expect(apiGet("/dossiers/")).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining("injoignable"),
    })
  })
})

describe("langue des requêtes", () => {
  const adaptateurInitial = axios.defaults.adapter

  afterEach(() => {
    api.defaults.adapter = adaptateurInitial
    setApiLanguage("fr")
  })

  it("envoie la langue de l'interface dans Accept-Language", async () => {
    // Les libellés du serveur (`*_display`, alertes) suivent cet en-tête :
    // sans lui, l'interface anglaise afficherait des statuts en français.
    let recu: string | undefined
    api.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
      recu = config.headers["Accept-Language"] as string | undefined
      return { status: 200, statusText: "", headers: {}, config, data: {} }
    }

    setApiLanguage("en")
    await apiGet("/me/")

    expect(recu).toBe("en")
  })
})
