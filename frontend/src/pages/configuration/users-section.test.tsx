import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { UsersSection } from "@/pages/configuration/users-section"
import type { AccountUser } from "@/lib/types"

const resetTwoFactor = vi.fn()
const fetchUsers = vi.fn()

function compte(overrides: Partial<AccountUser>): AccountUser {
  return {
    id: 7,
    username: "togo.innov",
    first_name: "Ama",
    last_name: "Togo",
    email: "ama.togo@innovpharma.net",
    is_active: true,
    role: "dm",
    countries: [1],
    countries_detail: [{ id: 1, name: "Togo", code: "TG", country_ref: "TG-01" }],
    must_change_password: false,
    totp_confirmed: true,
    ...overrides,
  }
}

vi.mock("@/lib/accounts", () => ({
  fetchUsers: (...args: unknown[]) => fetchUsers(...args),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  resetTwoFactor: (...args: unknown[]) => resetTwoFactor(...args),
  fetchPermissionMatrix: () =>
    Promise.resolve({
      roles: [
        { value: "super_admin", label: "Super administrateur", siege: true },
        { value: "dm", label: "DM", siege: false },
      ],
      capabilities: [],
      editable: false,
      note: "",
    }),
}))

vi.mock("@/lib/countries", () => ({
  fetchCountries: () => Promise.resolve({ count: 0, next: null, previous: null, results: [] }),
}))

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: { id: 99 },
    can: () => true,
  }),
}))

function page(users: AccountUser[]) {
  return { count: users.length, next: null, previous: null, results: users }
}

describe("UsersSection — double authentification", () => {
  beforeEach(() => {
    resetTwoFactor.mockReset()
    fetchUsers.mockReset()
  })

  it("montre l'état de la 2FA de chaque compte", async () => {
    fetchUsers.mockResolvedValue(
      page([compte({}), compte({ id: 8, username: "benin.innov", totp_confirmed: false })]),
    )
    render(<UsersSection />)

    expect(await screen.findByText("2FA active")).toBeInTheDocument()
    expect(screen.getByText("2FA à enrôler")).toBeInTheDocument()
  })

  it("ne propose la réinitialisation qu'à un compte enrôlé", async () => {
    fetchUsers.mockResolvedValue(
      page([compte({}), compte({ id: 8, username: "benin.innov", totp_confirmed: false })]),
    )
    render(<UsersSection />)

    expect(
      await screen.findByRole("button", {
        name: "Réinitialiser la double authentification de togo.innov",
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", {
        name: "Réinitialiser la double authentification de benin.innov",
      }),
    ).toBeNull()
  })

  it("demande confirmation avant de réinitialiser, puis appelle le serveur", async () => {
    fetchUsers.mockResolvedValue(page([compte({})]))
    resetTwoFactor.mockResolvedValue(compte({ totp_confirmed: false }))
    render(<UsersSection />)

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Réinitialiser la double authentification de togo.innov",
      }),
    )

    // Rien n'est envoyé à l'ouverture du dialogue.
    expect(await screen.findByRole("dialog")).toBeInTheDocument()
    expect(resetTwoFactor).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole("button", { name: "Réinitialiser la 2FA" }))

    await waitFor(() => expect(resetTwoFactor).toHaveBeenCalledWith(7))
    // La liste est relue : l'état affiché suit le serveur.
    await waitFor(() => expect(fetchUsers).toHaveBeenCalledTimes(2))
  })

  it("garde le dialogue ouvert et montre l'erreur du serveur", async () => {
    fetchUsers.mockResolvedValue(page([compte({})]))
    resetTwoFactor.mockRejectedValue(new Error("Hors de votre hiérarchie."))
    render(<UsersSection />)

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Réinitialiser la double authentification de togo.innov",
      }),
    )
    fireEvent.click(await screen.findByRole("button", { name: "Réinitialiser la 2FA" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Hors de votre hiérarchie.")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })
})
