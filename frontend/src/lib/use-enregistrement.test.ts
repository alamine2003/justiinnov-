import { act, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ApiError } from "./api"
import { messageDErreur, useEnregistrement } from "./use-enregistrement"

describe("messageDErreur", () => {
  it("préfère le message de l'erreur, sinon celui donné", () => {
    expect(messageDErreur(new Error("Refusé par le serveur"), "Défaut")).toBe("Refusé par le serveur")
    expect(messageDErreur("pas une erreur", "Défaut")).toBe("Défaut")
    expect(messageDErreur(undefined, "Défaut")).toBe("Défaut")
  })
})

describe("useEnregistrement", () => {
  it("signale l'envoi pendant l'écriture, puis l'éteint", async () => {
    const { result } = renderHook(() => useEnregistrement("Défaut"))
    let terminer: () => void = () => undefined
    let abouti: Promise<boolean> = Promise.resolve(false)

    act(() => {
      abouti = result.current.enregistrer(
        () => new Promise<void>((resolve) => (terminer = resolve)),
      )
    })
    expect(result.current.saving).toBe(true)

    await act(async () => {
      terminer()
      await abouti
    })
    expect(result.current.saving).toBe(false)
    expect(result.current.error).toBeNull()
    await expect(abouti).resolves.toBe(true)
  })

  it("efface l'erreur précédente au nouvel envoi", async () => {
    const { result } = renderHook(() => useEnregistrement("Défaut"))
    act(() => result.current.setError("Motif requis"))
    expect(result.current.error).toBe("Motif requis")

    await act(async () => {
      await result.current.enregistrer(async () => undefined)
    })
    expect(result.current.error).toBeNull()
  })

  it("affiche le message de l'erreur, sinon le message donné, et dit l'échec", async () => {
    const { result } = renderHook(() => useEnregistrement("Enregistrement impossible"))

    let abouti = true
    await act(async () => {
      abouti = await result.current.enregistrer(async () => {
        throw new Error("Ligne déjà constatée")
      })
    })
    expect(abouti).toBe(false)
    expect(result.current.error).toBe("Ligne déjà constatée")
    expect(result.current.saving).toBe(false)

    await act(async () => {
      await result.current.enregistrer(() => Promise.reject("illisible"))
    })
    expect(result.current.error).toBe("Enregistrement impossible")
  })

  it("laisse une fonction lire le refus, et taire l'en-tête", async () => {
    const lus: unknown[] = []
    const { result } = renderHook(() =>
      useEnregistrement((err) => {
        lus.push(err)
        return err instanceof ApiError && err.fields.note ? null : "Autre refus"
      }),
    )
    const refus = new ApiError(400, "Requête invalide", { note: ["Motif trop court"] })

    await act(async () => {
      await result.current.enregistrer(() => Promise.reject(refus))
    })
    expect(lus).toEqual([refus])
    expect(result.current.error).toBeNull()

    await act(async () => {
      await result.current.enregistrer(() => Promise.reject(new Error("x")))
    })
    expect(result.current.error).toBe("Autre refus")
  })

  it("n'écrit qu'une fois ce qu'on lui confie, dans l'ordre", async () => {
    const { result } = renderHook(() => useEnregistrement("Défaut"))
    const etapes: string[] = []
    await act(async () => {
      await result.current.enregistrer(async () => {
        etapes.push("appel")
        await Promise.resolve()
        etapes.push("relecture")
        etapes.push("fermeture")
      })
    })
    expect(etapes).toEqual(["appel", "relecture", "fermeture"])
  })
})
