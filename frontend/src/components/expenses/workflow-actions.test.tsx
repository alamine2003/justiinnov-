import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { WorkflowActions } from "./workflow-actions"
import type { Permissions } from "@/lib/types"

const DROITS: Record<string, Partial<Permissions>> = {
  saisie: { record_expenses: true, validate_expenses: false },
  controle: { record_expenses: false, validate_expenses: true },
  lecture: { record_expenses: false, validate_expenses: false },
}

let profil: keyof typeof DROITS = "saisie"

vi.mock("@/context/auth", () => ({
  useAuth: () => ({
    can: (permission: keyof Permissions) =>
      Boolean(DROITS[profil][permission]),
  }),
}))

function afficher(status: Parameters<typeof WorkflowActions>[0]["status"]) {
  return render(
    <WorkflowActions status={status} onTransition={vi.fn()} />,
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

  it("propose au contrôleur de justifier ou non une dépense soumise", () => {
    profil = "controle"
    const { container } = afficher("submitted")

    expect(container.textContent).toContain("Marquer justifié")
    expect(container.textContent).toContain("Marquer non justifié")
  })

  it("n'offre aucun retour au brouillon depuis une dépense non justifiée", () => {
    // L'argent est sorti : la dépense ne se réécrit pas.
    profil = "saisie"
    const { container } = afficher("unjustified")

    expect(container.textContent).not.toContain("Soumettre")
  })

  it("laisse le contrôleur justifier après coup une dépense non justifiée", () => {
    profil = "controle"
    const { container } = afficher("unjustified")

    expect(container.textContent).toContain("Marquer justifié")
  })

  it("n'affiche rien sur une dépense clôturée", () => {
    profil = "controle"
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
