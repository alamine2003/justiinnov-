import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { WorkflowActions } from "./workflow-actions"

type Props = Parameters<typeof WorkflowActions>[0]

/**
 * Le serveur a déjà appliqué rôle, état, quatre yeux et politique du circuit
 * dans `allowed_actions` : le composant n'a ni compte courant ni droits à
 * lire, il propose ce qu'on lui donne.
 */
function afficher(allowedActions: Props["allowedActions"], props: Partial<Props> = {}) {
  const complet = { allowedActions, onTransition: vi.fn(), ...props } as Props
  return render(<WorkflowActions {...complet} />)
}

describe("WorkflowActions — allowed_actions du serveur", () => {
  it("propose exactement les transitions données", () => {
    afficher(["review", "reject"])

    expect(screen.getByRole("button", { name: "Mettre en contrôle" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Marquer non justifié" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Marquer justifié" })).toBeNull()
  })

  it("propose la soumission d'un dossier quand le serveur l'ouvre", () => {
    afficher(["submit"], { subject: "dossier" })

    expect(screen.getByRole("button", { name: "Soumettre" })).toBeInTheDocument()
  })

  it("ne propose jamais de soumettre une ligne seule : le dossier emporte ses lignes", () => {
    const { container } = afficher(["submit"])

    expect(container.textContent).toBe("")
  })

  it("vide, ne propose rien", () => {
    const { container } = afficher([])

    expect(container.textContent).toBe("")
  })

  it("ignore une action inconnue de l'interface", () => {
    // « Rouvrir » a son propre bouton, hors du circuit.
    afficher(["reopen", "reject"], { subject: "dossier" })

    expect(screen.getAllByRole("button")).toHaveLength(1)
    expect(screen.getByRole("button", { name: "Marquer non justifié" })).toBeInTheDocument()
  })

  it("propose la clôture quand le serveur l'ouvre", () => {
    afficher(["close"], { subject: "dossier" })

    expect(screen.getByRole("button", { name: "Clôturer" })).toBeInTheDocument()
  })
})

describe("dossier", () => {
  it("dit dans le dialogue que toutes les lignes doivent déjà être justifiées", () => {
    afficher(["justify"], { subject: "dossier" })

    fireEvent.click(screen.getByRole("button", { name: "Marquer justifié" }))

    expect(screen.getByRole("dialog")).toHaveTextContent(/toutes les lignes doivent déjà être justifiées/i)
  })
})

describe("action sans dialogue", () => {
  it("affiche l'échec une seule fois et ne laisse aucune promesse non gérée", async () => {
    const onTransition = vi.fn().mockRejectedValue(new Error("Deux personnes sont nécessaires."))
    render(<WorkflowActions allowedActions={["review"]} onTransition={onTransition} />)

    fireEvent.click(screen.getByRole("button", { name: "Mettre en contrôle" }))

    const alertes = await screen.findAllByRole("alert")
    expect(alertes).toHaveLength(1)
    expect(alertes[0]).toHaveTextContent("Deux personnes sont nécessaires.")
    // Le bouton redevient utilisable.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Mettre en contrôle" })).toBeEnabled(),
    )
  })

  it("remet l'échec à la page quand elle le demande, sans l'afficher ici", async () => {
    const onError = vi.fn()
    const onTransition = vi.fn().mockRejectedValue(new Error("Refusé."))
    render(
      <WorkflowActions allowedActions={["review"]} onTransition={onTransition} onError={onError} />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Mettre en contrôle" }))

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Refusé."))
    expect(screen.queryByRole("alert")).toBeNull()
  })
})

describe("dialogue de justification", () => {
  it("propose le montant de la dépense par défaut et l'envoie en chaîne", async () => {
    const onTransition = vi.fn().mockResolvedValue(undefined)
    render(
      <WorkflowActions
        allowedActions={["justify", "reject"]}
        amount="1500.00"
        currency="XOF"
        onTransition={onTransition}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Marquer justifié" }))
    const champ = screen.getByLabelText(/Montant justifié/) as HTMLInputElement
    expect(champ.value).toBe("1500.00")

    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }))

    await waitFor(() =>
      expect(onTransition).toHaveBeenCalledWith("justify", {
        note: "",
        justified_amount: "1500.00",
      }),
    )
  })

  it("accepte la virgule décimale et la normalise", async () => {
    const onTransition = vi.fn().mockResolvedValue(undefined)
    render(
      <WorkflowActions allowedActions={["justify"]} amount="1500.00" onTransition={onTransition} />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Marquer justifié" }))
    fireEvent.change(screen.getByLabelText(/Montant justifié/), {
      target: { value: "1 200,50" },
    })
    fireEvent.change(screen.getByLabelText(/Note/), { target: { value: "partiel" } })
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }))

    await waitFor(() =>
      expect(onTransition).toHaveBeenCalledWith("justify", {
        note: "partiel",
        justified_amount: "1200.50",
      }),
    )
  })

  it("refuse un montant qui n'est pas un nombre sans appeler le serveur", () => {
    const onTransition = vi.fn()
    render(<WorkflowActions allowedActions={["justify"]} amount="10" onTransition={onTransition} />)

    fireEvent.click(screen.getByRole("button", { name: "Marquer justifié" }))
    fireEvent.change(screen.getByLabelText(/Montant justifié/), {
      target: { value: "abc" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }))

    expect(screen.getByRole("alert")).toHaveTextContent("montant")
    expect(onTransition).not.toHaveBeenCalled()
  })
})

describe("dialogue de rejet", () => {
  it("exige un motif", () => {
    const onTransition = vi.fn()
    render(<WorkflowActions allowedActions={["reject"]} onTransition={onTransition} />)

    fireEvent.click(screen.getByRole("button", { name: "Marquer non justifié" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }))

    expect(screen.getByRole("alert")).toHaveTextContent("motivé")
    expect(onTransition).not.toHaveBeenCalled()
  })

  it("reste ouvert et affiche l'erreur du serveur une seule fois en cas d'échec", async () => {
    const onTransition = vi.fn().mockRejectedValue(new Error("Deux personnes sont nécessaires."))
    render(<WorkflowActions allowedActions={["reject"]} onTransition={onTransition} />)

    fireEvent.click(screen.getByRole("button", { name: "Marquer non justifié" }))
    fireEvent.change(screen.getByLabelText("Motif du refus"), {
      target: { value: "Facture illisible" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }))

    const alertes = await screen.findAllByRole("alert")
    expect(alertes).toHaveLength(1)
    expect(alertes[0]).toHaveTextContent("Deux personnes sont nécessaires.")
    expect(screen.getByLabelText("Motif du refus")).toHaveValue("Facture illisible")
  })
})
