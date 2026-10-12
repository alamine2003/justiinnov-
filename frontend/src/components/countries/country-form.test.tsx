import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { CountryForm } from "./country-form"

vi.mock("@/lib/countries", () => ({
  fetchAvailableCountries: () =>
    Promise.resolve([
      { code: "BJ", name: "Bénin", currency: "XOF" },
      { code: "CG", name: "Congo", currency: "XAF" },
    ]),
}))

/** Décision 121 : la devise officielle du pays choisi se propose d'office. */
describe("CountryForm — devise", () => {
  it("propose la devise officielle du pays choisi, qui reste modifiable", async () => {
    render(<CountryForm open onOpenChange={() => {}} onSave={vi.fn()} />)

    const pays = await screen.findByRole("combobox", { name: "Pays" })
    await screen.findByRole("option", { name: "Bénin (BJ)" })
    fireEvent.change(pays, { target: { value: "BJ" } })
    const devise = screen.getByLabelText("Devise (ISO 4217)")
    expect(devise).toHaveValue("XOF")

    fireEvent.change(pays, { target: { value: "CG" } })
    expect(devise).toHaveValue("XAF")

    fireEvent.change(devise, { target: { value: "xof" } })
    expect(devise).toHaveValue("XOF")
  })
})
