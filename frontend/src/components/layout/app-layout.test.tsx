import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppLayout } from "./app-layout"
import { BRAND, copyright } from "@/lib/brand"
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

function monter(chemin = "/") {
  return render(
    <MemoryRouter initialEntries={[chemin]}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="*" element={<p>Page</p>} />
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

  it("porte la version et le copyright en pied de menu, et la version seule repliée", () => {
    monter()

    const menu = barre().closest("aside") as HTMLElement
    expect(menu).toHaveTextContent(`Version ${BRAND.version}`)
    expect(menu).toHaveTextContent(copyright())

    fireEvent.click(screen.getByRole("button", { name: "Réduire le menu" }))

    expect(menu).toHaveTextContent(`Version ${BRAND.version}`)
    expect(menu).not.toHaveTextContent(copyright())
  })

  it("garde le périmètre dans l'en-tête", () => {
    monter()

    expect(screen.getByRole("banner")).toHaveTextContent("Siège — tous pays")
  })

  /**
   * Régression : « Retour » se taisait dès `lg` sur toute page dont le
   * parent est l'accueil, `/dossiers` compris — que le menu ne propose
   * plus. Et sa ligne, restée au-dessus d'une fiche, la faisait défiler :
   * la hauteur laissée à la page doit la retrancher.
   */
  it("tait « Retour » dès lg sur une entrée du menu seulement, et retranche sa ligne ailleurs", () => {
    const { unmount } = monter("/registre")
    expect(screen.getByRole("button", { name: "Retour" }).parentElement).toHaveClass("lg:hidden")
    expect(screen.getByRole("main")).not.toHaveClass("[--retour:2.75rem]")
    unmount()

    monter("/dossiers")
    expect(screen.getByRole("button", { name: "Retour" }).parentElement).not.toHaveClass("lg:hidden")
    expect(screen.getByRole("main")).toHaveClass("[--retour:2.75rem]")
  })
})
