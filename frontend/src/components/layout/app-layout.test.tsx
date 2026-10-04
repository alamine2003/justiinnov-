import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppLayout } from "./app-layout"
import type { Me } from "@/lib/types"

let droits = new Set<string>()
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: {
      has_global_scope: true,
      countries: [],
      must_change_password: false,
      totp_required: false,
      totp_confirmed: true,
    } as Partial<Me>,
    can: (cle: string) => droits.has(cle),
    logout: vi.fn(),
  }),
}))
vi.mock("@/components/layout/notification-bell", () => ({ NotificationBell: () => null }))
vi.mock("@/components/layout/user-menu", () => ({ UserMenu: () => null, SUPERVISION_PATH: "/supervision" }))
vi.mock("@/components/layout/language-toggle", () => ({ LanguageToggle: () => null }))
vi.mock("@/components/layout/theme-toggle", () => ({ ThemeToggle: () => null }))
vi.mock("@/lib/install-prompt", () => ({ useInstallPrompt: () => ({ available: false, install: vi.fn() }) }))

function monter() {
  return render(
    <MemoryRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<p>Accueil</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

const barre = () => screen.getByRole("navigation", { name: "Navigation principale" })

beforeEach(() => {
  droits = new Set(["audit.read", "configuration.manage"])
  localStorage.clear()
})
afterEach(() => localStorage.clear())

/**
 * La navigation est une barre latérale dès `lg` : les sept entrées du siège
 * y tiennent avec leur libellé, groupées. Repliée, elle ne garde que les
 * icônes — chaque entrée garde alors son nom accessible.
 */
describe("AppLayout — barre latérale", () => {
  it("range les entrées par groupe, dans l'ordre", () => {
    monter()

    expect(within(barre()).getAllByRole("link").map((lien) => lien.textContent)).toEqual([
      "Pilotage", "Projets", "Registre", "Budgets", "Pays", "Audit", "Configuration",
    ])
    for (const groupe of ["Suivi", "Budget", "Contrôle", "Administration"]) {
      expect(within(barre()).getByText(groupe)).toBeInTheDocument()
    }
  })

  it("tait un groupe que les droits du compte laissent vide", () => {
    droits = new Set()

    monter()

    expect(within(barre()).queryByText("Contrôle")).toBeNull()
    expect(within(barre()).queryByText("Administration")).toBeNull()
    expect(within(barre()).queryByRole("link", { name: "Audit" })).toBeNull()
  })

  it("se replie en gardant le nom de chaque entrée, et s'en souvient", () => {
    const { unmount } = monter()

    const reduire = screen.getByRole("button", { name: "Réduire le menu" })
    expect(reduire).toHaveAttribute("aria-expanded", "true")
    fireEvent.click(reduire)

    expect(screen.getByRole("button", { name: "Déplier le menu" })).toHaveAttribute("aria-expanded", "false")
    expect(within(barre()).getByRole("link", { name: "Projets" })).toHaveAttribute("title", "Projets")
    expect(within(barre()).getByText("Projets")).toHaveClass("sr-only")
    expect(within(barre()).queryByText("Suivi")).toBeNull()

    unmount()
    monter()
    expect(screen.getByRole("button", { name: "Déplier le menu" })).toBeInTheDocument()
  })

  it("garde le périmètre dans l'en-tête", () => {
    monter()

    expect(screen.getByRole("banner")).toHaveTextContent("Siège — tous pays")
  })
})
