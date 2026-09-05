import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { UsersSection } from "@/pages/configuration/users-section"
import type { AccountUser } from "@/lib/types"

const resetTwoFactor = vi.fn()
const fetchUsers = vi.fn()
const createUser = vi.fn()
const updateUser = vi.fn()
const logout = vi.fn()
const fetchCountry = vi.fn()
let monRole = "super_admin"

function compte(overrides: Partial<AccountUser>): AccountUser {
  return {
    id: 7,
    username: "togo.innov",
    first_name: "Ama",
    last_name: "Togo",
    email: "ama.togo@innovpharma.net",
    is_active: true,
    role: "manager",
    countries: [1],
    countries_detail: [
      { id: 1, name: "Togo", code: "TG", country_ref: "TG-01", timezone: "Africa/Lome", currency: "XOF" },
    ],
    teams: [],
    teams_detail: [],
    must_change_password: false,
    totp_confirmed: true,
    ...overrides,
  }
}

vi.mock("@/lib/accounts", () => ({
  fetchUsers: (...args: unknown[]) => fetchUsers(...args),
  createUser: (...args: unknown[]) => createUser(...args),
  updateUser: (...args: unknown[]) => updateUser(...args),
  resetTwoFactor: (...args: unknown[]) => resetTwoFactor(...args),
  fetchPermissionMatrix: () =>
    Promise.resolve({
      roles: [
        { value: "super_admin", label: "Super administrateur", siege: true, always_global: true },
        { value: "admin", label: "Administrateur", siege: true, always_global: true },
        { value: "dm", label: "DM", siege: true, always_global: false },
        { value: "manager", label: "Manager", siege: false, always_global: false },
      ],
      capabilities: [],
      editable: false,
      note: "",
    }),
}))

vi.mock("@/lib/countries", () => ({
  fetchCountries: () =>
    Promise.resolve({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 1, name: "Togo", code: "TG", country_ref: "TG-01", is_active: true }],
    }),
  fetchCountry: (...args: unknown[]) => fetchCountry(...args),
}))

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    me: { id: 99, username: "admin.innov", role: monRole },
    can: () => true,
    logout: (...args: unknown[]) => logout(...args),
  }),
}))

function page(users: AccountUser[]) {
  return { count: users.length, next: null, previous: null, results: users }
}

describe("UsersSection — double authentification", () => {
  beforeEach(() => {
    resetTwoFactor.mockReset()
    fetchUsers.mockReset()
    logout.mockReset()
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

  it("prévient et déconnecte proprement quand on réinitialise sa propre 2FA", async () => {
    fetchUsers.mockResolvedValue(page([compte({ id: 99, username: "admin.innov" })]))
    resetTwoFactor.mockResolvedValue(compte({ id: 99, totp_confirmed: false }))
    logout.mockResolvedValue(undefined)
    render(<UsersSection />)

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Réinitialiser la double authentification de admin.innov",
      }),
    )

    expect(await screen.findByRole("dialog")).toHaveTextContent(/votre propre compte/)

    fireEvent.click(screen.getByRole("button", { name: "Réinitialiser la 2FA" }))

    await waitFor(() => expect(resetTwoFactor).toHaveBeenCalledWith(99))
    // Le serveur fermerait la plateforme à la prochaine requête : la
    // session se ferme d'elle-même, sans attendre un 403.
    await waitFor(() => expect(logout).toHaveBeenCalledOnce())
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

describe("UsersSection — périmètre selon le rôle", () => {
  beforeEach(() => {
    fetchUsers.mockReset()
    fetchUsers.mockResolvedValue(page([]))
    createUser.mockReset()
    updateUser.mockReset()
    fetchCountry.mockReset()
    fetchCountry.mockResolvedValue({ id: 1, teams: [] })
    monRole = "super_admin"
  })

  it("exige un pays pour un compte de pays", async () => {
    render(<UsersSection />)
    fireEvent.click(await screen.findByRole("button", { name: "Créer un compte" }))

    const role = await screen.findByLabelText("Rôle")
    fireEvent.change(role, { target: { value: "manager" } })

    expect(screen.getByText("Un manager est rattaché à au moins un pays.")).toBeInTheDocument()
  })

  it("propose le périmètre, facultatif, à un compte du siège restrictible", async () => {
    // Le DM est au siège : sans pays coché il voit tout, un pays coché le
    // restreint. La liste reste donc affichée.
    render(<UsersSection />)
    fireEvent.click(await screen.findByRole("button", { name: "Créer un compte" }))

    const role = await screen.findByLabelText("Rôle")
    fireEvent.change(role, { target: { value: "dm" } })

    expect(screen.getByText(/Facultatif pour un compte du siège/)).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: /Togo/ })).toBeInTheDocument()
  })
})

describe("UsersSection — rôles toujours globaux", () => {
  beforeEach(() => {
    fetchUsers.mockReset()
    fetchUsers.mockResolvedValue(page([]))
    createUser.mockReset()
    createUser.mockResolvedValue(compte({ id: 12 }))
    monRole = "super_admin"
  })

  it("ne propose aucun pays à un rôle toujours global et envoie un périmètre vide", async () => {
    render(<UsersSection />)
    fireEvent.click(await screen.findByRole("button", { name: "Créer un compte" }))

    const role = await screen.findByLabelText("Rôle")
    fireEvent.change(role, { target: { value: "admin" } })

    expect(screen.queryByRole("checkbox", { name: /Togo/ })).toBeNull()
    expect(screen.getByText(/aucun périmètre à cocher/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("Identifiant"), { target: { value: "rh.innov" } })
    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "rh@innovpharma.net" } })
    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "provisoire" } })
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(createUser).toHaveBeenCalledOnce())
    expect(createUser.mock.calls[0][0]).toMatchObject({ role: "admin", countries: [] })
  })

  it("ne propose pas « super administrateur » à un administrateur qui ne l'est pas", async () => {
    monRole = "admin"
    render(<UsersSection />)
    fireEvent.click(await screen.findByRole("button", { name: "Créer un compte" }))

    const options = (await screen.findAllByRole("option")).map((o) => o.textContent)
    expect(options.some((o) => o?.includes("Super administrateur"))).toBe(false)
    expect(options.some((o) => o?.includes("Administrateur"))).toBe(true)
  })
})

describe("UsersSection — modification", () => {
  beforeEach(() => {
    fetchUsers.mockReset()
    updateUser.mockReset()
    updateUser.mockResolvedValue(compte({}))
    fetchCountry.mockReset()
    fetchCountry.mockResolvedValue({ id: 1, teams: [] })
    monRole = "super_admin"
  })

  it("laisse l'identifiant en lecture seule et ne le renvoie pas", async () => {
    fetchUsers.mockResolvedValue(page([compte({})]))
    render(<UsersSection />)

    fireEvent.click(await screen.findByRole("button", { name: "Modifier togo.innov" }))

    const identifiant = await screen.findByLabelText("Identifiant")
    expect(identifiant).toHaveAttribute("readonly")
    expect(screen.getByText(/ne se change pas/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(updateUser).toHaveBeenCalledOnce())
    expect(updateUser.mock.calls[0][1]).not.toHaveProperty("username")
  })

  it("propose les équipes des pays cochés et les envoie", async () => {
    fetchUsers.mockResolvedValue(page([compte({ teams: [] })]))
    fetchCountry.mockResolvedValue({
      id: 1,
      teams: [
        { id: 4, name: "Commerciale", country: 1, is_active: true },
        { id: 5, name: "Dormante", country: 1, is_active: false },
      ],
    })
    render(<UsersSection />)

    fireEvent.click(await screen.findByRole("button", { name: "Modifier togo.innov" }))

    const equipe = await screen.findByRole("checkbox", { name: /Commerciale/ })
    expect(screen.queryByRole("checkbox", { name: /Dormante/ })).toBeNull()
    fireEvent.click(equipe)
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(updateUser).toHaveBeenCalledOnce())
    expect(updateUser.mock.calls[0][1]).toMatchObject({ teams: [4] })
    expect(fetchCountry).toHaveBeenCalledWith(1)
  })
})
