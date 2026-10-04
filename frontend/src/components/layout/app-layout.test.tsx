import { render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { AppLayout } from "./app-layout"
import type { Me } from "@/lib/types"

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: {
      has_global_scope: true,
      countries: [],
      must_change_password: false,
      totp_required: false,
      totp_confirmed: true,
    } as Partial<Me>,
    can: () => true,
    logout: vi.fn(),
  }),
}))
vi.mock("@/components/layout/notification-bell", () => ({ NotificationBell: () => null }))
vi.mock("@/components/layout/user-menu", () => ({ UserMenu: () => null, SUPERVISION_PATH: "/supervision" }))
vi.mock("@/components/layout/language-toggle", () => ({ LanguageToggle: () => null }))
vi.mock("@/components/layout/theme-toggle", () => ({ ThemeToggle: () => null }))
vi.mock("@/lib/install-prompt", () => ({ useInstallPrompt: () => ({ available: false, install: vi.fn() }) }))

/**
 * Régression : à 768 px, les sept entrées du siège débordaient de la barre
 * (163 px). De `lg` à `xl`, elles n'y gardent que leur icône ; leur libellé,
 * masqué à l'œil, doit rester leur nom accessible.
 */
describe("AppLayout — barre de navigation", () => {
  it("garde un nom à chaque entrée réduite à son icône", () => {
    render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<p>Accueil</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    const barre = screen.getByRole("navigation", { name: "Navigation principale" })
    const noms = within(barre).getAllByRole("link").map((lien) => lien.textContent)
    expect(noms).toEqual([
      "Pilotage", "Projets", "Registre", "Budgets", "Pays", "Audit", "Configuration",
    ])
    for (const libelle of within(barre).getAllByText(/./)) {
      expect(libelle.className).toContain("sr-only xl:not-sr-only")
    }
  })
})
