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

/**
 * Une ligne porte le projet de son dossier (décision 102) : le formulaire
 * ne le propose plus et ne l'envoie pas — le serveur le recopie. Seul un
 * dossier du projet « Historique » garde le choix (décision 105).
 */
describe("ExpenseForm — projet de la ligne", () => {
  const projet = { id: 9, name: "Gamme pédiatrique" } as Parameters<typeof ExpenseForm>[0]["projects"][number]

  it("hors « Historique », ni champ ni projet envoyé", async () => {
    const onSave = afficher()
    expect(screen.queryByLabelText("Projet")).toBeNull()
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Taxi" } })
    fireEvent.change(screen.getByLabelText(/^Dépense/), { target: { value: "2500" } })

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    expect(onSave.mock.calls[0][0]).not.toHaveProperty("project")
  })

  it("à la modification non plus : le projet en base n'est pas effacé", async () => {
    const onSave = afficher({
      editing: {
        id: 5, title: "Taxi", amount: "2500", project: 9, team: 4,
        date: "2026-03-15T10:00:00Z", payment_method: "cash",
      } as Parameters<typeof ExpenseForm>[0]["editing"],
    })

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    expect(onSave.mock.calls[0][0]).not.toHaveProperty("project")
  })

  it("dans « Historique », le champ s'affiche et le projet part", async () => {
    const onSave = afficher({ projects: [projet] })
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Taxi" } })
    fireEvent.change(screen.getByLabelText(/^Dépense/), { target: { value: "2500" } })
    fireEvent.change(screen.getByLabelText("Projet"), { target: { value: "9" } })

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    expect(onSave.mock.calls[0][0]).toMatchObject({ project: 9 })
  })
})

/**
 * Décision 127, achevée en 2.4.8 : le jour se choisit au calendrier de
 * l'application, l'heure à part ; la valeur part à l'heure du pays.
 */
describe("ExpenseForm — date et heure", () => {
  it("compose le jour du calendrier et l'heure, à l'heure du pays", async () => {
    const onSave = afficher()
    const maintenant = new Date()
    const mois = String(maintenant.getMonth() + 1).padStart(2, "0")
    const premier = `${maintenant.getFullYear()}-${mois}-01`
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Taxi" } })
    fireEvent.change(screen.getByLabelText(/^Dépense/), { target: { value: "2500" } })

    fireEvent.click(screen.getByRole("button", { name: /Date et heure/ }))
    const jour = await waitFor(() => {
      const bouton = document.querySelector<HTMLButtonElement>(`[data-day="${premier}"] button`)
      if (!bouton) throw new Error("jour absent")
      return bouton
    })
    fireEvent.click(jour)
    fireEvent.change(screen.getByLabelText("Heure"), { target: { value: "08:15" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    // Lomé vit à UTC+0 : l'instant envoyé est l'heure saisie.
    expect(onSave.mock.calls[0][0]).toMatchObject({ date: `${premier}T08:15:00.000Z` })
  })

  it("lit l'heure dans le fuseau du pays, à UTC+1 comme au Gabon", async () => {
    const onSave = afficher({ timezone: "Africa/Libreville" })
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Taxi" } })
    fireEvent.change(screen.getByLabelText(/^Dépense/), { target: { value: "2500" } })
    fireEvent.change(screen.getByLabelText("Heure"), { target: { value: "08:15" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    // 08:15 à Libreville, c'est 07:15 en temps universel, le même jour.
    expect(onSave.mock.calls[0][0].date).toMatch(/T07:15:00\.000Z$/)
  })

  it("complète une heure tapée vite et la garde sur 24 heures", () => {
    afficher()
    const heure = screen.getByLabelText("Heure") as HTMLInputElement
    fireEvent.change(heure, { target: { value: "9h05" } })
    fireEvent.blur(heure)
    expect(heure.value).toBe("09:05")
  })

  it("complète l'heure même validée par Entrée, sans quitter le champ", async () => {
    const onSave = afficher()
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Taxi" } })
    fireEvent.change(screen.getByLabelText(/^Dépense/), { target: { value: "2500" } })
    const heure = screen.getByLabelText("Heure")
    fireEvent.change(heure, { target: { value: "8:15" } })
    fireEvent.submit(heure.closest("form")!)

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    expect(onSave.mock.calls[0][0].date).toMatch(/T08:15:00\.000Z$/)
  })

  it("refuse une heure qui n'existe pas, en le disant", async () => {
    const onSave = afficher()
    fireEvent.change(screen.getByLabelText(/^Libellé/), { target: { value: "Taxi" } })
    fireEvent.change(screen.getByLabelText(/^Dépense/), { target: { value: "2500" } })
    fireEvent.change(screen.getByLabelText("Heure"), { target: { value: "25:70" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Indiquez l'heure sur 24 heures")
    expect(onSave).not.toHaveBeenCalled()
  })
})
