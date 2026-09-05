import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ExpenseForm } from "./expense-form"

function afficher(props: Partial<Parameters<typeof ExpenseForm>[0]> = {}) {
  const onSave = vi.fn().mockResolvedValue(undefined)
  render(
    <ExpenseForm
      open
      onOpenChange={vi.fn()}
      onSave={onSave}
      editing={null}
      teams={[
        {
          id: 4,
          country: 1,
          country_name: "Togo",
          name: "Commerciale",
          description: "",
          is_active: true,
          created_at: "",
          updated_at: "",
        },
      ]}
      projects={[]}
      beneficiaries={[]}
      expenseTitles={[]}
      marketingCategories={[]}
      managers={[]}
      currency="FCFA"
      timezone="Africa/Lome"
      {...props}
    />,
  )
  return onSave
}

describe("ExpenseForm — devise du décaissement", () => {
  it("réclame le montant décaissé quand une devise est saisie sans montant", () => {
    // Le champ du pays est désactivé dès qu'une devise est saisie :
    // « montant requis » ne dirait pas lequel manque.
    const onSave = afficher()
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Hôtel" } })
    fireEvent.change(screen.getByLabelText(/Devise/), { target: { value: "EUR" } })

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    expect(screen.getByRole("alert")).toHaveTextContent(/montant décaissé/i)
    expect(onSave).not.toHaveBeenCalled()
  })

  it("envoie la devise et son montant, sans montant du pays", async () => {
    const onSave = afficher()
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Hôtel" } })
    fireEvent.change(screen.getByLabelText(/Devise/), { target: { value: "eur" } })
    fireEvent.change(screen.getByLabelText("Montant décaissé"), { target: { value: "120,50" } })

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    expect(onSave.mock.calls[0][0]).toMatchObject({
      original_currency: "EUR",
      original_amount: "120.50",
      amount: undefined,
    })
  })
})

describe("ExpenseForm — équipe d'un manager rattaché", () => {
  it("exige une équipe quand le serveur l'exigerait", () => {
    // Le serveur répond 400 « Choisissez une de vos équipes. » : autant le
    // dire avant d'envoyer.
    const onSave = afficher({ teamRequired: true })
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Taxi" } })
    fireEvent.change(screen.getByLabelText(/^Dépense/), { target: { value: "2500" } })

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    expect(screen.getByRole("alert")).toHaveTextContent("Choisissez une de vos équipes.")
    expect(onSave).not.toHaveBeenCalled()
  })

  it("n'exige rien des autres", async () => {
    const onSave = afficher()
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Taxi" } })
    fireEvent.change(screen.getByLabelText(/^Dépense/), { target: { value: "2500" } })

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    expect(onSave.mock.calls[0][0]).toMatchObject({ amount: "2500", team: null })
  })
})
