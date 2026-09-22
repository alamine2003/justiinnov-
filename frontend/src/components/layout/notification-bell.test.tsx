import { act, render } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { NotificationBell } from "./notification-bell"
import { ApiError } from "@/lib/api"

const fetchUnreadCount = vi.fn()
vi.mock("@/lib/reporting", () => ({
  fetchUnreadCount: () => fetchUnreadCount(),
  fetchNotifications: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}))

/**
 * Le compteur est sondé toutes les minutes. Quand le serveur répond 503 avec
 * `Retry-After`, il demande un répit : les sondages qui tombent avant cette
 * date sont sautés, au lieu de le relancer à chaque minute.
 */
describe("NotificationBell — répit demandé par le serveur", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    fetchUnreadCount.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("saute les sondages qui tombent avant la fin du délai Retry-After", async () => {
    fetchUnreadCount
      .mockRejectedValueOnce(new ApiError(503, "Indisponible", {}, null, 150))
      .mockResolvedValue({ unread: 0 })
    render(
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>,
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(fetchUnreadCount).toHaveBeenCalledTimes(1)

    // À 60 s et 120 s le répit court encore : rien ne part.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000)
    })
    expect(fetchUnreadCount).toHaveBeenCalledTimes(1)

    // À 180 s le délai de 150 s est passé : le sondage reprend.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(fetchUnreadCount).toHaveBeenCalledTimes(2)
  })
})
