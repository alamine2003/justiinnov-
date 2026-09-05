import { act, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n"
import { TotpNotice } from "./totp-notice"

const enrolTwoFactor = vi.fn()

vi.mock("@/lib/accounts", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/accounts")>()
  return {
    ...original,
    enrolTwoFactor: () => enrolTwoFactor(),
    confirmTwoFactor: vi.fn(),
  }
})

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: { totp_confirmed: false, totp_required: false },
    refreshProfile: vi.fn(),
  }),
}))

describe("TotpNotice — enrôlement", () => {
  beforeEach(() => {
    enrolTwoFactor.mockReset()
    enrolTwoFactor.mockResolvedValue({
      otpauth_uri: "otpauth://totp/x",
      qr_png_base64: "AAAA",
      secret: "JBSWY3DPEHPK3PXP",
    })
  })

  afterEach(async () => {
    await act(() => i18n.changeLanguage("fr"))
  })

  it("ne demande le secret qu'une fois, même quand la langue change", async () => {
    // Chaque appel régénère le secret : un QR remplacé sous les yeux de la
    // personne n'aurait plus rien à voir avec ce que son application a
    // scanné. Le changement de langue re-rend l'écran ; il ne doit pas
    // relancer l'enrôlement.
    render(
      <MemoryRouter>
        <TotpNotice />
      </MemoryRouter>,
    )

    expect(await screen.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument()

    await act(() => i18n.changeLanguage("en"))
    expect(await screen.findByRole("button", { name: "Confirm" })).toBeInTheDocument()

    expect(enrolTwoFactor).toHaveBeenCalledOnce()
    expect(screen.getByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument()
  })
})
