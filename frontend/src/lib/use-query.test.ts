import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
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
