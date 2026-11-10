import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useEquipesDesPays } from "@/lib/use-equipes-des-pays"

const fetchCountry = vi.fn()

vi.mock("@/lib/countries", () => ({
  fetchCountry: (...args: unknown[]) => fetchCountry(...args),
}))

function fiche(id: number) {
  return {
    id,
    teams: [
      { id: id * 10, name: `Active ${id}`, is_active: true },
      { id: id * 10 + 1, name: `Retiree ${id}`, is_active: false },
    ],
  }
}

describe("useEquipesDesPays", () => {
  beforeEach(() => {
    fetchCountry.mockReset()
    fetchCountry.mockImplementation((id: number) => Promise.resolve(fiche(id)))
  })

  it("ne demande rien quand les équipes ne s'appliquent pas", () => {
    const { result } = renderHook(() => useEquipesDesPays([1, 2], false))
    expect(fetchCountry).not.toHaveBeenCalled()
    expect(result.current).toEqual({})
  })

  it("lit les équipes actives de chaque pays coché", async () => {
    const { result } = renderHook(() => useEquipesDesPays([1, 2], true))
    await waitFor(() => expect(Object.keys(result.current)).toHaveLength(2))
    expect(result.current[1]).toEqual([{ id: 10, name: "Active 1", is_active: true }])
    expect(result.current[2]).toEqual([{ id: 20, name: "Active 2", is_active: true }])
  })

  it("ne demande qu'une fois la fiche de chaque pays, à mesure des coches", async () => {
    const { result, rerender } = renderHook(({ ids }) => useEquipesDesPays(ids, true), {
      initialProps: { ids: [1] },
    })
    await waitFor(() => expect(result.current[1]).toBeDefined())
    rerender({ ids: [1, 2] })
    await waitFor(() => expect(result.current[2]).toBeDefined())
    rerender({ ids: [2, 1] })
    expect(fetchCountry.mock.calls.map(([id]) => id)).toEqual([1, 2])
  })

  it("donne une liste vide sur une fiche illisible, et retente au cochage suivant", async () => {
    fetchCountry.mockRejectedValueOnce(new Error("hors ligne"))
    const { result, rerender } = renderHook(({ ids }) => useEquipesDesPays(ids, true), {
      initialProps: { ids: [3] },
    })
    await waitFor(() => expect(result.current[3]).toEqual([]))
    rerender({ ids: [] })
    rerender({ ids: [3] })
    await waitFor(() => expect(result.current[3]).toHaveLength(1))
    expect(fetchCountry).toHaveBeenCalledTimes(2)
  })
})
