import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { CountryForm } from "./country-form"

vi.mock("@/lib/countries", () => ({
  fetchAvailableCountries: () =>
    Promise.resolve([
      { code: "BJ", name: "Bénin", currency: "XOF", timezone: "Africa/Porto-Novo", timezones: ["Africa/Porto-Novo"] },
      { code: "CG", name: "Congo", currency: "XAF", timezone: "Africa/Brazzaville", timezones: ["Africa/Brazzaville"] },
      {
        code: "CD", name: "République démocratique du Congo", currency: "CDF",
        timezone: "Africa/Kinshasa", timezones: ["Africa/Kinshasa", "Africa/Lubumbashi"],
      },
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

/**
 * Décision 128 : le fuseau se choisit dans la liste du pays, il ne se tape
 * plus — « UTC » et « GMT » avaient été tapés pour des pays à UTC+1.
 */
describe("CountryForm — fuseau", () => {
  it("propose le fuseau officiel du pays choisi, et les deux de la RDC", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(<CountryForm open onOpenChange={() => {}} onSave={onSave} />)

    const pays = await screen.findByRole("combobox", { name: "Pays" })
    await screen.findByRole("option", { name: "Bénin (BJ)" })
    const fuseau = screen.getByRole("combobox", { name: "Fuseau horaire" })
    expect(fuseau).toBeDisabled()

    fireEvent.change(pays, { target: { value: "BJ" } })
    expect(fuseau).toHaveValue("Africa/Porto-Novo")
    expect(fuseau).toBeEnabled()

    fireEvent.change(pays, { target: { value: "CD" } })
    expect(fuseau).toHaveValue("Africa/Kinshasa")
    expect(screen.getByRole("option", { name: "Africa/Lubumbashi" })).toBeInTheDocument()
    expect(screen.queryByRole("option", { name: "Africa/Porto-Novo" })).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))
    await vi.waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0][0]).toMatchObject({ code: "CD", timezone: "Africa/Kinshasa" })
  })

  it("montre un fuseau hors liste comme à corriger, sans le changer de lui-même", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <CountryForm
        open
        onOpenChange={() => {}}
        onSave={onSave}
        initial={{ name: "Gabon", code: "GA", currency: "XAF", currency_symbol: "FCFA", timezone: "GMT", is_active: true }}
        fuseaux={["Africa/Libreville"]}
      />,
    )

    const fuseau = screen.getByRole("combobox", { name: "Fuseau horaire" })
    expect(fuseau).toHaveValue("GMT")
    expect(screen.getByRole("option", { name: "GMT (à corriger)" })).toBeInTheDocument()
    expect(screen.getByText(/n'est pas celui du pays/)).toBeInTheDocument()

    fireEvent.change(fuseau, { target: { value: "Africa/Libreville" } })
    expect(screen.queryByText(/n'est pas celui du pays/)).toBeNull()
    expect(screen.queryByRole("option", { name: "GMT (à corriger)" })).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))
    await vi.waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0][0]).toMatchObject({ timezone: "Africa/Libreville" })
  })

  it("ne dit rien d'un pays dont le fuseau est le sien", () => {
    render(
      <CountryForm
        open
        onOpenChange={() => {}}
        onSave={vi.fn()}
        initial={{ name: "Togo", code: "TG", currency: "XOF", currency_symbol: "FCFA", timezone: "Africa/Lome", is_active: true }}
        fuseaux={["Africa/Lome"]}
      />,
    )

    expect(screen.getByRole("combobox", { name: "Fuseau horaire" })).toHaveValue("Africa/Lome")
    expect(screen.queryByText(/n'est pas celui du pays/)).toBeNull()
  })
})
