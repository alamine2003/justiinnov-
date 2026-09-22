import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api"
import { useQuery } from "@/lib/use-query"

/**
 * Régression : à l'échec, `useQuery` posait le nouveau jeton — donc `loading`
 * retombait — mais gardait les données de la clé précédente. Sur la liste des
 * dossiers, cliquer « Justifié » sur une requête qui échoue laissait les
 * cinquante brouillons à l'écran, sous le filtre « Justifié » et un bandeau
 * d'erreur : un résultat faux, présenté comme un résultat.
 */
describe("useQuery", () => {
  it("efface les données de la clé précédente quand la nouvelle échoue", async () => {
    const { result, rerender } = renderHook(
      ({ cle, fetcher }: { cle: string; fetcher: () => Promise<string> }) =>
        useQuery(cle, fetcher),
      { initialProps: { cle: "draft", fetcher: () => Promise.resolve("brouillons") } },
    )

    await waitFor(() => expect(result.current.data).toBe("brouillons"))

    rerender({ cle: "justified", fetcher: () => Promise.reject(new Error("502")) })

    await waitFor(() => expect(result.current.error).toBe("502"))
    expect(result.current.data).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it("garde ce qui est à l'écran quand un rechargement de la même clé échoue", async () => {
    let echoue = false
    const { result } = renderHook(() =>
      useQuery("draft", () =>
        echoue ? Promise.reject(new Error("502")) : Promise.resolve("brouillons"),
      ),
    )

    await waitFor(() => expect(result.current.data).toBe("brouillons"))

    echoue = true
    act(() => result.current.reload())

    await waitFor(() => expect(result.current.error).toBe("502"))
    expect(result.current.data).toBe("brouillons")
  })

  it("ignore la réponse d'une requête abandonnée", async () => {
    const lent = vi.fn(
      (signal: AbortSignal) =>
        new Promise<string>((resolve, reject) => {
          setTimeout(() => (signal.aborted ? reject(new Error("abandon")) : resolve("lent")), 20)
        }),
    )
    const { result, rerender } = renderHook(
      ({ cle }: { cle: string }) =>
        useQuery(cle, cle === "a" ? lent : () => Promise.resolve("rapide")),
      { initialProps: { cle: "a" } },
    )

    rerender({ cle: "b" })

    await waitFor(() => expect(result.current.data).toBe("rapide"))
    expect(result.current.error).toBeNull()
  })
})

/**
 * Régression : en passant du dossier 12 au dossier 13, la page de détail
 * gardait le dossier 12 à l'écran — sous l'adresse du 13 — le temps de la
 * réponse. Une liste qu'on filtre a le droit de rester lisible ; une entité
 * identifiée par l'URL, non.
 */
describe("useQuery — keepPreviousData", () => {
  function lent(valeur: string) {
    return (signal: AbortSignal) =>
      new Promise<string>((resolve, reject) => {
        setTimeout(() => (signal.aborted ? reject(new Error("abandon")) : resolve(valeur)), 30)
      })
  }

  it("rend `data` nul tant que la nouvelle clé n'a pas répondu, avec keepPreviousData: false", async () => {
    const { result, rerender } = renderHook(
      ({ cle }: { cle: string }) =>
        useQuery(cle, cle === "a" ? () => Promise.resolve("dossier 12") : lent("dossier 13"), {
          keepPreviousData: false,
        }),
      { initialProps: { cle: "a" } },
    )
    await waitFor(() => expect(result.current.data).toBe("dossier 12"))

    rerender({ cle: "b" })

    expect(result.current.data).toBeNull()
    expect(result.current.loading).toBe(true)
    expect(result.current.refreshing).toBe(false)
    await waitFor(() => expect(result.current.data).toBe("dossier 13"))
  })

  it("garde le résultat précédent par défaut, pour une liste qu'on filtre", async () => {
    const { result, rerender } = renderHook(
      ({ cle }: { cle: string }) =>
        useQuery(cle, cle === "a" ? () => Promise.resolve("page 1") : lent("page 2")),
      { initialProps: { cle: "a" } },
    )
    await waitFor(() => expect(result.current.data).toBe("page 1"))

    rerender({ cle: "b" })

    expect(result.current.data).toBe("page 1")
    expect(result.current.refreshing).toBe(true)
    await waitFor(() => expect(result.current.data).toBe("page 2"))
  })

  it("garde ce qui est à l'écran pendant un rechargement de la même clé, même sans keepPreviousData", async () => {
    let appels = 0
    const { result } = renderHook(() =>
      useQuery("a", () => Promise.resolve(`lecture ${(appels += 1)}`), { keepPreviousData: false }),
    )
    await waitFor(() => expect(result.current.data).toBe("lecture 1"))

    act(() => result.current.reload())

    expect(result.current.data).toBe("lecture 1")
    expect(result.current.refreshing).toBe(true)
    await waitFor(() => expect(result.current.data).toBe("lecture 2"))
  })
})

/**
 * Un 503 ou un 429 porte parfois `Retry-After` : le serveur dit quand
 * revenir. La requête est rejouée une fois, après ce délai, puis on attend
 * un geste de l'utilisateur — pas de sondage sans fin.
 */
describe("useQuery — Retry-After", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("recharge une seule fois après le délai demandé par le serveur", async () => {
    vi.useFakeTimers()
    let appels = 0
    const fetcher = vi.fn(() => {
      appels += 1
      return appels === 1
        ? Promise.reject(new ApiError(503, "Service indisponible", {}, null, 3))
        : Promise.resolve("revenu")
    })
    const { result } = renderHook(() => useQuery("a", fetcher))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.error).toBe("Service indisponible")
    expect(result.current.retryAfter).toBe(3)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_999)
    })
    expect(fetcher).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.data).toBe("revenu")
    expect(result.current.retryAfter).toBeNull()
  })

  it("ne rejoue pas un second échec, et borne le délai à une minute", async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn(() =>
      Promise.reject(new ApiError(503, "Service indisponible", {}, null, 3_600)),
    )
    renderHook(() => useQuery("a", fetcher))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(59_999)
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(fetcher).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_600_000)
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
})
