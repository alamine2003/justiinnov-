import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { UserMenu } from "./user-menu"

// jsdom n'a pas d'événement pointeur ; le menu de base-ui en construit un au
// clic sur le déclencheur. Un MouseEvent en tient lieu, le test ne lit que
// l'état du menu.
if (typeof window.PointerEvent === "undefined") {
  Object.defineProperty(window, "PointerEvent", { value: MouseEvent, writable: true })
}

const me = vi.fn()

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: me(),
    can: () => false,
  }),
}))

function ouvrirMenu() {
  render(
    <MemoryRouter>
      <UserMenu onLogout={vi.fn()} />
    </MemoryRouter>,
  )
  const trigger = screen.getByRole("button", { name: "Menu du compte" })
  // base-ui ouvre le menu sur la séquence pointeur complète : un simple
  // `click` de jsdom, sans `pointerdown`/`mousedown`, ne suffit pas. Le menu
  // s'ouvre de façon synchrone (act l'attend) : une attente asynchrone
  // (`findBy…`) tournerait indéfiniment, le repositionnement de base-ui
  // n'ayant ni `ResizeObserver` ni image de la mise en page sous jsdom.
  fireEvent.pointerDown(trigger)
  fireEvent.mouseDown(trigger)
  fireEvent.click(trigger)
  return screen.getByRole("menu")
}

describe("UserMenu — version de l'API", () => {
  it("affiche la version renvoyée par le serveur, sous l'identité", () => {
    me.mockReturnValue({
      username: "togo.innov",
      role_display: "Manager",
      totp_confirmed: true,
      api_version: "sha-abc123def456",
    })

    const menu = ouvrirMenu()

    expect(screen.getByText("Version de l'API sha-abc123def456")).toBeInTheDocument()
    // Ce n'est pas une action : un simple repère, jamais un élément cliquable.
    expect(
      menu.querySelector('[data-slot="dropdown-menu-item"]')?.textContent,
    ).not.toContain("sha-abc123def456")
  })

  it("ne montre rien quand le serveur ne renseigne pas la version", () => {
    me.mockReturnValue({
      username: "togo.innov",
      role_display: "Manager",
      totp_confirmed: false,
      api_version: "",
    })

    ouvrirMenu()

    expect(screen.queryByText(/Version de l'API/)).not.toBeInTheDocument()
  })
})
