import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { RefreshIndicator } from "./refresh-indicator"

/**
 * Trois pages posaient un `aria-label` sur l'icône qui tourne pendant une
 * relecture : un `<svg>` sans rôle, que les lecteurs d'écran ignorent. Le
 * libellé est donné en `sr-only`, l'icône est masquée.
 */
describe("RefreshIndicator", () => {
  it("donne son libellé aux lecteurs d'écran et masque l'icône", () => {
    render(<RefreshIndicator label="Actualisation" />)

    const statut = screen.getByRole("status")
    expect(statut).toHaveTextContent("Actualisation")
    expect(screen.getByText("Actualisation")).toHaveClass("sr-only")
    expect(statut.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
    expect(statut.querySelector("svg")).not.toHaveAttribute("aria-label")
  })
})
