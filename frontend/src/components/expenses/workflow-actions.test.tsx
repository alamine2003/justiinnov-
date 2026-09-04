import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { WorkflowActions } from "./workflow-actions"
import type { Permissions } from "@/lib/types"

/** Un profil par acteur du circuit : manager, DM, DF, administrateur. */
const DROITS: Record<string, Partial<Permissions>> = {
  saisie: { record_expenses: true, review_expenses: false, validate_expenses: false },
  controle: { record_expenses: false, review_expenses: true, validate_expenses: false },
  constat: { record_expenses: false, review_expenses: false, validate_expenses: true },
  siege: { record_expenses: false, review_expenses: true, validate_expenses: true },
  // Serveur qui ne connaît pas encore `review_expenses`.
  ancien: { record_expenses: false, validate_expenses: true },
  lecture: { record_expenses: false, review_expenses: false, validate_expenses: false },
}

let profil: keyof typeof DROITS = "saisie"
let controleObligatoire = false

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    can: (permission: keyof Permissions) =>
      Boolean(DROITS[profil][permission]),
    me: {
      workflow: { require_review_step: controleObligatoire },
      permissions: DROITS[profil],
    },
  }),
}))

function afficher(
  status: Parameters<typeof WorkflowActions>[0]["status"],
  props: Partial<Parameters<typeof WorkflowActions>[0]> = {},
) {
  return render(
    <WorkflowActions status={status} onTransition={vi.fn()} {...props} />,
  )
}

describe("WorkflowActions", () => {
  it("propose la soumission d'un brouillon à qui sait saisir", () => {
    profil = "saisie"
    afficher("draft")

    expect(screen.getByRole("button", { name: "Soumettre" })).toBeInTheDocument()
  })

  it("ne propose pas de valider à qui ne fait que saisir", () => {
    profil = "saisie"
    afficher("submitted")

    expect(screen.queryByRole("button", { name: /justifié/i })).toBeNull()
  })

  it("propose au DF de justifier ou non une dépense soumise", () => {
    profil = "constat"
    controleObligatoire = false
    const { container } = afficher("submitted")

    expect(container.textContent).toContain("Marquer justifié")
    expect(container.textContent).toContain("Marquer non justifié")
  })

  it("ne propose la mise en contrôle qu'au DM, et rien d'autre", () => {
    // Le DM met en contrôle ; il ne constate pas.
    profil = "controle"
    afficher("submitted")

    expect(screen.getByRole("button", { name: "Mettre en contrôle" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Marquer justifié" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Marquer non justifié" })).toBeNull()
  })

  it("ne propose pas la mise en contrôle au DF", () => {
    profil = "constat"
    afficher("submitted")

    expect(screen.queryByRole("button", { name: "Mettre en contrôle" })).toBeNull()
  })

  it("laisse un serveur sans `review_expenses` ranger la mise en contrôle avec le constat", () => {
    profil = "ancien"
    afficher("submitted")

    expect(screen.getByRole("button", { name: "Mettre en contrôle" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Marquer justifié" })).toBeInTheDocument()
  })

  it("n'affiche rien au DM sur une dépense en contrôle", () => {
    profil = "controle"
    const { container } = afficher("in_review")

    expect(container.textContent).toBe("")
  })

  it("impose de mettre en contrôle avant de justifier quand la politique l'exige", () => {
    // `require_review_step` : le serveur refuse `justify` depuis « Soumis ».
    // Le bouton ne menait qu'à un message d'erreur.
    profil = "siege"
    controleObligatoire = true
    afficher("submitted")

    expect(screen.queryByRole("button", { name: "Marquer justifié" })).toBeNull()
    expect(screen.getByRole("button", { name: "Mettre en contrôle" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Marquer non justifié" })).toBeInTheDocument()
    controleObligatoire = false
  })

  it("laisse justifier depuis « En contrôle » même quand le contrôle est obligatoire", () => {
    profil = "constat"
    controleObligatoire = true
    afficher("in_review")

    expect(screen.getByRole("button", { name: "Marquer justifié" })).toBeInTheDocument()
    controleObligatoire = false
  })

  it("n'offre aucun retour au brouillon depuis une dépense non justifiée", () => {
    // L'argent est sorti : la dépense ne se réécrit pas.
    profil = "saisie"
    const { container } = afficher("unjustified")

    expect(container.textContent).not.toContain("Soumettre")
  })

  it("laisse le DF justifier après coup une dépense non justifiée", () => {
    profil = "constat"
    const { container } = afficher("unjustified")

    expect(container.textContent).toContain("Marquer justifié")
  })

  it("n'affiche rien sur une dépense clôturée", () => {
    profil = "siege"
    const { container } = afficher("closed")

    expect(container.textContent).toBe("")
  })

  it("n'affiche rien à un rôle en lecture seule", () => {
    profil = "lecture"
    const { container } = afficher("submitted")

    expect(container.textContent).toBe("")
  })
})

describe("hideSubmit", () => {
  it("masque « Soumettre » quand le dossier est encore un brouillon", () => {
    // Le serveur refuse : une ligne ne devance pas son dossier. Le bouton ne
    // menait qu'à un message d'erreur.
    profil = "saisie"

    render(
      <WorkflowActions status="draft" onTransition={vi.fn()} hideSubmit />,
    )

    expect(screen.queryByRole("button", { name: /Soumettre/ })).toBeNull()
  })

  it("le laisse quand le dossier est déjà déclaré", () => {
    profil = "saisie"

    afficher("draft")

    expect(screen.getByRole("button", { name: /Soumettre/ })).toBeTruthy()
  })
})

describe("dialogue de justification", () => {
  it("propose le montant de la dépense par défaut et l'envoie en chaîne", async () => {
    profil = "constat"
    const onTransition = vi.fn().mockResolvedValue(undefined)
    render(
      <WorkflowActions
        status="in_review"
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
    profil = "constat"
    const onTransition = vi.fn().mockResolvedValue(undefined)
    render(
      <WorkflowActions status="in_review" amount="1500.00" onTransition={onTransition} />,
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
    profil = "constat"
    const onTransition = vi.fn()
    render(<WorkflowActions status="in_review" amount="10" onTransition={onTransition} />)

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
    profil = "constat"
    const onTransition = vi.fn()
    render(<WorkflowActions status="submitted" onTransition={onTransition} />)

    fireEvent.click(screen.getByRole("button", { name: "Marquer non justifié" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }))

    expect(screen.getByRole("alert")).toHaveTextContent("motivé")
    expect(onTransition).not.toHaveBeenCalled()
  })

  it("reste ouvert et affiche l'erreur du serveur en cas d'échec", async () => {
    profil = "constat"
    const onTransition = vi.fn().mockRejectedValue(new Error("Deux personnes sont nécessaires."))
    render(<WorkflowActions status="submitted" onTransition={onTransition} />)

    fireEvent.click(screen.getByRole("button", { name: "Marquer non justifié" }))
    fireEvent.change(screen.getByLabelText("Motif du refus"), {
      target: { value: "Facture illisible" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Deux personnes sont nécessaires.")
    expect(screen.getByLabelText("Motif du refus")).toHaveValue("Facture illisible")
  })
})
