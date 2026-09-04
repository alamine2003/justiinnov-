import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  REFERENTIEL_TTL_MS,
  invalidateReferentiel,
  isTruncated,
  useReferentiel,
} from "./referentiel"

describe("useReferentiel", () => {
  beforeEach(() => invalidateReferentiel())
  afterEach(() => vi.useRealTimers())

  it("partage la même requête entre deux composants", async () => {
    const fetcher = vi.fn(async () => ["Togo"])

    const a = renderHook(() => useReferentiel("pays", fetcher))
    const b = renderHook(() => useReferentiel("pays", fetcher))

    await waitFor(() => expect(a.result.current.data).toEqual(["Togo"]))
    await waitFor(() => expect(b.result.current.data).toEqual(["Togo"]))
    expect(fetcher).toHaveBeenCalledOnce()
  })

  it("sert le cache tant qu'il est frais, puis recharge", async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn(async () => ["Togo"])

    const premier = renderHook(() => useReferentiel("pays", fetcher))
    await act(async () => {
      await vi.runAllTimersAsync()
    })
    premier.unmount()

    renderHook(() => useReferentiel("pays", fetcher))
    await act(async () => {
      await vi.runAllTimersAsync()
    })
    expect(fetcher).toHaveBeenCalledOnce()

    vi.setSystemTime(Date.now() + REFERENTIEL_TTL_MS + 1)
    renderHook(() => useReferentiel("pays", fetcher))
    await act(async () => {
      await vi.runAllTimersAsync()
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it("recharge après une invalidation manuelle", async () => {
    const fetcher = vi.fn(async () => ["Togo"])
    const { result } = renderHook(() => useReferentiel("pays", fetcher))
    await waitFor(() => expect(result.current.data).toEqual(["Togo"]))

    act(() => invalidateReferentiel("pays"))

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
  })

  it("ne met pas un échec en cache", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error("panne"))
      .mockResolvedValue(["Togo"])
    const { result } = renderHook(() => useReferentiel("pays", fetcher))
    await waitFor(() => expect(result.current.error).toBe("panne"))

    act(() => result.current.reload())

    await waitFor(() => expect(result.current.data).toEqual(["Togo"]))
  })
})

describe("isTruncated", () => {
  it("signale une liste dont le serveur connaît plus d'éléments", () => {
    expect(isTruncated({ count: 3, next: null, previous: null, results: [1, 2, 3] })).toBe(false)
    expect(isTruncated({ count: 250, next: "…", previous: null, results: [1] })).toBe(true)
    expect(isTruncated(null)).toBe(false)
  })
})
