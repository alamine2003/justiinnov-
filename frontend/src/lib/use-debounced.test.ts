import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useDebouncedValue } from "./use-debounced"

describe("useDebouncedValue", () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it("ne propage la valeur qu'après le délai", () => {
    const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 300), {
      initialProps: { v: "" },
    })

    rerender({ v: "lom" })
    expect(result.current).toBe("")

    act(() => vi.advanceTimersByTime(299))
    expect(result.current).toBe("")

    act(() => vi.advanceTimersByTime(1))
    expect(result.current).toBe("lom")
  })

  it("ne garde que la dernière frappe", () => {
    const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 300), {
      initialProps: { v: "" },
    })

    rerender({ v: "l" })
    act(() => vi.advanceTimersByTime(100))
    rerender({ v: "lo" })
    act(() => vi.advanceTimersByTime(100))
    rerender({ v: "lom" })
    act(() => vi.advanceTimersByTime(300))

    expect(result.current).toBe("lom")
  })
})
