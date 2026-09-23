import { StrictMode, useState } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import App from "@/App"
import { AuthProvider } from "@/context/auth"
import { ThemeProvider } from "@/context/theme"
import { ApiError, setToken } from "@/lib/api"
import type { Me, PermissionMatrix, Permissions } from "@/lib/types"
import { PERMISSIONS_DU_PAYS } from "@/test/permissions-fixtures"

// jsdom n'a pas d'événement pointeur ; l'interrupteur de base-ui en construit
// un au clic.
if (typeof window.PointerEvent === "undefined") {
  Object.defineProperty(window, "PointerEvent", { value: MouseEvent, writable: true })
}

const fetchMe = vi.fn()
const updatePermissionMatrix = vi.fn()
const apiPost = vi.fn()

/** La matrice que la page de configuration simulée reçoit du serveur. */
const { matrice } = vi.hoisted(() => ({
  matrice: {
    roles: [
      { value: "super_admin", label: "Super administrateur", siege: true, always_global: true, assignable: true },
      { value: "admin", label: "Administrateur (RH)", siege: true, always_global: true, assignable: true },
      { value: "manager", label: "Manager (pays)", siege: false, always_global: false, assignable: true },
    ],
    capabilities: [
      {
        key: "data.export",
        group: "Fichiers",
        label: "Exporter",
        description: "Telecharger le registre.",
        roles: ["admin", "super_admin"],
        default_roles: ["admin", "super_admin"],
        fixed_roles: ["admin", "super_admin"],
        locked_roles: [],
        settable_by_roles: ["admin", "super_admin"],
      },
    ],
    note: "",
  } as PermissionMatrix,
}))

vi.mock("@/lib/accounts", async (original) => ({
  ...(await original<typeof import("@/lib/accounts")>()),
  fetchMe: (...args: unknown[]) => fetchMe(...args),
  updatePermissionMatrix: (...args: unknown[]) => updatePermissionMatrix(...args),
}))
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  apiPost: (...args: unknown[]) => apiPost(...args),
}))

// Les pages réelles chargent des données ; ici seul le comportement de la
// garde et du fournisseur compte. Le tableau de bord porte un état local —
// un compteur — pour voir s'il survit à une relecture du profil.
vi.mock("@/components/layout/app-layout", async () => {
  const { Outlet } = await import("react-router-dom")
  return { AppLayout: () => <Outlet /> }
})
vi.mock("@/pages/dashboard", async () => {
  const { useAuth } = await import("@/context/use-auth")
  function DashboardPage() {
    const { me, refreshProfile } = useAuth()
    const [compteur, setCompteur] = useState(0)
    return (
      <div>
        <h1>Pilotage</h1>
        <p data-testid="compteur">{compteur}</p>
        <p data-testid="role">{me?.role_display}</p>
        <button type="button" onClick={() => setCompteur((c) => c + 1)}>
          Compter
        </button>
        <button type="button" onClick={() => void refreshProfile().catch(() => {})}>
          Relire
        </button>
      </div>
    )
  }
  return { DashboardPage }
})
vi.mock("@/pages/configuration", async () => {
  const { useState: useEtat } = await import("react")
  const { MatriceDesDroits } = await import("@/pages/configuration/permissions-section")
  // Comme la vraie page : la matrice rendue par le serveur après
  // l'enregistrement remplace celle affichée.
  function ConfigurationPage() {
    const [matrix, setMatrix] = useEtat(matrice)
    return <MatriceDesDroits matrix={matrix} onSaved={setMatrix} />
  }
  return { ConfigurationPage }
})

function profil(
  overrides: Partial<Omit<Me, "permissions">> & { permissions?: Partial<Permissions> } = {},
): Me {
  return {
    id: 1,
    username: "rh.innov",
    first_name: "",
    last_name: "",
    email: "",
    role: "admin",
    role_display: "Administrateur (RH)",
    countries: [],
    teams: [],
    has_global_scope: true,
    must_change_password: false,
    totp_required: false,
    totp_confirmed: true,
    language: "fr",
    supervision: false,
    workflow: { require_review_step: false },
    alert_thresholds: [80, 100],
    ...overrides,
    permissions: { ...PERMISSIONS_DU_PAYS, ...overrides.permissions },
  }
}

/** Le serveur met un temps réel à répondre : c'est pendant ce temps que le chargeur s'affichait. */
function repondLentement(valeur: Me) {
  return new Promise<Me>((resolve) => {
    setTimeout(() => resolve(valeur), 20)
  })
}

function ouvrir(chemin: string) {
  return render(
    <StrictMode>
      <ThemeProvider>
        <MemoryRouter initialEntries={[chemin]}>
          <AuthProvider>
            <App />
          </AuthProvider>
        </MemoryRouter>
      </ThemeProvider>
    </StrictMode>,
  )
}

beforeEach(() => {
  fetchMe.mockReset()
  updatePermissionMatrix.mockReset()
  apiPost.mockReset()
})

afterEach(() => {
  localStorage.clear()
})

/**
 * Régression : `refreshProfile` passait `loadingProfile` à vrai, et la garde
 * de routes rendait alors le chargeur plein écran à la place de l'application.
 * Chaque relecture du profil — après un réglage de la matrice des droits —
 * démontait toutes les pages : leur état local, et la confirmation
 * « Enregistré » avec.
 */
describe("AuthProvider — relecture du profil", () => {
  it("relit le profil en arrière-plan sans démonter la page ni son état", async () => {
    setToken("jeton")
    fetchMe.mockResolvedValue(profil())
    ouvrir("/")

    expect(await screen.findByRole("heading", { name: "Pilotage" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Compter" }))
    fireEvent.click(screen.getByRole("button", { name: "Compter" }))
    expect(screen.getByTestId("compteur")).toHaveTextContent("2")

    fetchMe.mockImplementation(() =>
      repondLentement(profil({ role_display: "Administrateur (RH) — relu" })),
    )
    fireEvent.click(screen.getByRole("button", { name: "Relire" }))

    await waitFor(() =>
      expect(screen.getByTestId("role")).toHaveTextContent("Administrateur (RH) — relu"),
    )
    // Le compteur est toujours là : la page n'a pas été démontée.
    expect(screen.getByTestId("compteur")).toHaveTextContent("2")
  })

  it("garde la confirmation « Enregistré » de la matrice des droits après la relecture", async () => {
    setToken("jeton")
    fetchMe.mockImplementation(() =>
      repondLentement(profil({ permissions: { "configuration.manage": true } })),
    )
    updatePermissionMatrix.mockResolvedValue({
      ...matrice,
      capabilities: [{ ...matrice.capabilities[0], roles: ["admin", "super_admin", "manager"] }],
    })
    ouvrir("/configuration")

    fireEvent.click(await screen.findByRole("switch", { name: "Exporter pour Manager (pays)" }))
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    expect(
      await screen.findByText("Droits enregistrés : ils s'appliquent dès maintenant."),
    ).toBeInTheDocument()
    await waitFor(() => expect(fetchMe.mock.calls.length).toBeGreaterThanOrEqual(2))
    expect(
      screen.getByText("Droits enregistrés : ils s'appliquent dès maintenant."),
    ).toBeInTheDocument()
  })
})

/**
 * Régression : un 403 sur `/api/me/` — compte sans profil rattaché — vidait
 * la session en silence, et l'écran de connexion réapparaissait sans un
 * mot. Le motif du serveur est désormais relancé, et affiché.
 */
describe("AuthProvider — connexion d'un compte sans profil", () => {
  it("affiche le motif du serveur sur l'écran de connexion et ne garde pas la session", async () => {
    apiPost.mockResolvedValue({ token: "jeton" })
    fetchMe.mockRejectedValue(new ApiError(403, "Aucun profil n'est rattaché à ce compte."))
    ouvrir("/login")

    // La page de connexion est chargée à la demande : on l'attend.
    fireEvent.change(await screen.findByLabelText("Identifiant"), {
      target: { value: "sans.profil" },
    })
    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "secret" } })
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Aucun profil n'est rattaché à ce compte.",
    )
    expect(screen.getByRole("heading", { name: "Connexion" })).toBeInTheDocument()
    expect(localStorage.getItem("justi_token")).toBeNull()
  })
})

describe("AuthProvider — session existante dont le profil est refusé", () => {
  it("montre le motif, propose de réessayer ou de se déconnecter, sans vider la session d'office", async () => {
    setToken("jeton")
    fetchMe.mockRejectedValue(new ApiError(403, "Aucun profil n'est rattaché à ce compte."))
    apiPost.mockResolvedValue({})
    ouvrir("/")

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Aucun profil n'est rattaché à ce compte.",
    )
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument()
    expect(localStorage.getItem("justi_token")).toBe("jeton")

    fireEvent.click(screen.getByRole("button", { name: "Déconnexion" }))

    expect(await screen.findByRole("heading", { name: "Connexion" })).toBeInTheDocument()
    expect(localStorage.getItem("justi_token")).toBeNull()
  })
})
