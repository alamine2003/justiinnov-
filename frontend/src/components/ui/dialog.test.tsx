import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

/**
 * Régression : `DialogContent` ne bornait pas sa hauteur. Centré en
 * `fixed top-1/2 -translate-y-1/2`, un formulaire long débordait par le haut
 * *et* par le bas, et comme un conteneur fixe ne se défile pas, le bouton de
 * soumission devenait inatteignable — mesuré à 797 px de contenu sur un écran
 * de 768 px, courant sur un portable. La borne appartient au composant : la
 * confier à l'appelant, c'est attendre qu'il l'oublie, et trois formulaires
 * sur cinq l'avaient oubliée.
 */
describe("DialogContent", () => {
  it("borne sa hauteur et défile", () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nouvelle enveloppe</DialogTitle>
            <DialogDescription>Attribuez un montant à un pays.</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>,
    )

    const contenu = screen.getByRole("dialog")

    expect(contenu.className).toContain("max-h-[90vh]")
    expect(contenu.className).toContain("overflow-y-auto")
  })
})
