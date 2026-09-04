import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import App from "@/App"
import type { Me, Permissions } from "@/lib/types"

function profil(overrides: Partial<Omit<Me, "permissions">> & { permissions?: Partial<Permissions> }): Me {
  return {
    id: 1,
    username: "togo.innov",
    first_name: "",
    last_name: "",
    email: "",
    role: "country_manager",
    role_display: "Responsable pays",
    countries: [{ id: 1, name: "Togo", code: "TG", country_ref: "TG" }],
    has_global_scope: false,
    must_change_password: false,
    workflow: { require_review_step: false },
    ...overrides,
    permissions: {
      manage_users: false,
      manage_countries: false,
      manage_subentities: false,
      manage_budgets: false,
      record_expenses: true,
      validate_expenses: false,
      view_audit: false,
      ...overrides.permissions,
    },
  }
}

let me: Me = profil({})

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    token: "jeton",
    isAuthenticated: true,
    me,
    loadingProfile: false,
    profileError: null,
    login: vi.fn(),
    logout: vi.fn(),
    refreshProfile: vi.fn(),
    replaceToken: vi.fn(),
    can: (permission: keyof Permissions) => Boolean(me.permissions[permission]),
  }),
}))

// Les pages réelles chargent des données ; ici seule la garde compte.
vi.mock("@/components/layout/app-layout", async () => {
  const { Outlet, useLocation } = await import("react-router-dom")
  function AppLayout() {
    const location = useLocation()
    const notice = (location.state as { notice?: string } | null)?.notice
    return (
      <div>
        <span data-testid="pathname">{location.pathname}</span>
        {notice && <p data-testid="notice">{notice}</p>}
        <Outlet />
      </div>
    )
  }
  return { AppLayout }
})
vi.mock("@/pages/dashboard", () => ({ DashboardPage: () => <h1>Pilotage</h1> }))
vi.mock("@/pages/configuration", () => ({ ConfigurationPage: () => <h1>Configuration</h1> }))
vi.mock("@/pages/audit/list", () => ({ AuditPage: () => <h1>Journal d'audit</h1> }))
vi.mock("@/pages/password", () => ({ PasswordPage: () => <h1>Choisissez votre mot de passe</h1> }))

function ouvrir(chemin: string) {
  return render(
    <MemoryRouter initialEntries={[chemin]}>
      <App />
    </MemoryRouter>,
  )
}

describe("garde des routes", () => {
  it("ramène un rôle pays au tableau de bord depuis la configuration", async () => {
    me = profil({})
    ouvrir("/configuration")

    expect(await screen.findByRole("heading", { name: "Pilotage" })).toBeInTheDocument()
    expect(screen.getByTestId("pathname")).toHaveTextContent("/")
    expect(screen.getByTestId("notice")).toHaveTextContent("Page réservée au siège")
  })

  it("ramène un rôle pays au tableau de bord depuis le journal d'audit", async () => {
    me = profil({})
    ouvrir("/audit")

    expect(await screen.findByRole("heading", { name: "Pilotage" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "Journal d'audit" })).toBeNull()
  })

  it("laisse le siège ouvrir la configuration", async () => {
    me = profil({ has_global_scope: true, permissions: { manage_users: true } })
    ouvrir("/configuration")

    expect(await screen.findByRole("heading", { name: "Configuration" })).toBeInTheDocument()
  })

  it("n'ouvre que l'écran de changement à un mot de passe provisoire", async () => {
    me = profil({ must_change_password: true })
    ouvrir("/dossiers")

    expect(
      await screen.findByRole("heading", { name: "Choisissez votre mot de passe" }),
    ).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId("pathname")).toHaveTextContent("/mot-de-passe"))
  })

  it("renvoie l'écran de changement vers l'accueil une fois le mot de passe remplacé", async () => {
    me = profil({})
    ouvrir("/mot-de-passe")

    expect(await screen.findByRole("heading", { name: "Pilotage" })).toBeInTheDocument()
  })
})
