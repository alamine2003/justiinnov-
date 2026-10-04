import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ThemeProvider } from "@/context/theme"
import { ApiError } from "@/lib/api"
import { LoginPage } from "@/pages/login"

const login = vi.fn()

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    isAuthenticated: false,
    login,
  }),
}))

/** Réponse du serveur quand la 2FA est confirmée et que le code manque ou est faux. */
function refusTotp(message: string) {
  return new ApiError(
    400,
    message,
    { code: [message] },
    { code: [message], totp_required: true },
  )
}

function afficher() {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

function saisirIdentifiants() {
  fireEvent.change(screen.getByLabelText("Identifiant"), { target: { value: "togo.innov" } })
  fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "secret" } })
  fireEvent.click(screen.getByRole("button", { name: "Se connecter" }))
}

describe("connexion avec double authentification", () => {
  beforeEach(() => {
    login.mockReset()
  })

  it("ne montre pas le champ du code au premier temps", () => {
    afficher()

    expect(screen.queryByLabelText("Code de double authentification")).toBeNull()
  })

  it("connecte en un temps un compte sans double authentification", async () => {
    login.mockResolvedValueOnce(undefined)
    afficher()

    saisirIdentifiants()

    await waitFor(() => expect(login).toHaveBeenCalledWith("togo.innov", "secret", undefined))
    expect(screen.queryByLabelText("Code de double authentification")).toBeNull()
  })

  it("exige le code et garde les identifiants saisis quand le serveur le réclame", async () => {
    login.mockRejectedValueOnce(refusTotp("Ce champ est obligatoire."))
    afficher()

    saisirIdentifiants()

    await waitFor(() =>
      expect(screen.getByLabelText("Code de double authentification")).toBeRequired(),
    )
    expect(screen.getByLabelText("Identifiant")).toHaveValue("togo.innov")
    expect(screen.getByLabelText("Mot de passe")).toHaveValue("secret")
    // Aucun code n'a encore été présenté : rien à reprocher.
    expect(screen.queryByRole("alert")).toBeNull()
    expect(login).toHaveBeenCalledWith("togo.innov", "secret", undefined)
  })

  it("envoie le code avec les identifiants", async () => {
    login.mockRejectedValueOnce(refusTotp("Ce champ est obligatoire.")).mockResolvedValueOnce(undefined)
    afficher()

    saisirIdentifiants()
    const champ = await screen.findByLabelText("Code de double authentification")
    // Le champ apparaît avec le focus : il ne reste que le code à saisir.
    await waitFor(() => expect(champ).toHaveFocus())
    fireEvent.change(champ, { target: { value: "123456" } })
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }))

    await waitFor(() => expect(login).toHaveBeenLastCalledWith("togo.innov", "secret", "123456"))
  })

  it("affiche le refus d'un code faux sans vider le champ", async () => {
    login
      .mockRejectedValueOnce(refusTotp("Ce champ est obligatoire."))
      .mockRejectedValueOnce(refusTotp("Code invalide."))
    afficher()

    saisirIdentifiants()
    const champ = await screen.findByLabelText("Code de double authentification")
    fireEvent.change(champ, { target: { value: "000000" } })
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Code invalide.")
    expect(screen.getByLabelText("Code de double authentification")).toHaveValue("000000")
  })

  it("exige un code une fois qu'il est demandé, sans appeler le serveur", async () => {
    login.mockRejectedValueOnce(refusTotp("Ce champ est obligatoire."))
    afficher()

    saisirIdentifiants()
    await screen.findByLabelText("Code de double authentification")
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("code")
    expect(login).toHaveBeenCalledTimes(1)
  })
})

/**
 * Un compte dont le serveur refuse le profil (403 sur `/api/me/`, sans
 * profil rattaché par exemple) : `login` rejette avec le motif du serveur,
 * et l'écran de connexion l'affiche. Que `refreshProfile` relance bien ce
 * refus au lieu de vider la session en silence se vérifie avec le vrai
 * `AuthProvider`, dans `context/auth.test.tsx`.
 */
describe("connexion refusée par le profil", () => {
  it("affiche le motif du serveur dans l'erreur du formulaire", async () => {
    login.mockRejectedValueOnce(new ApiError(403, "Aucun profil n'est rattaché à ce compte."))
    afficher()

    saisirIdentifiants()

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Aucun profil n'est rattaché à ce compte.",
    )
    expect(screen.getByLabelText("Identifiant")).toHaveValue("togo.innov")
  })

  it("repart du premier temps quand le mot de passe change", async () => {
    login.mockRejectedValueOnce(refusTotp("Ce champ est obligatoire."))
    afficher()

    saisirIdentifiants()
    await screen.findByLabelText("Code de double authentification")
    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "autre" } })

    expect(screen.queryByLabelText("Code de double authentification")).toBeNull()
    expect(screen.queryByText(/Mot de passe accepté/)).toBeNull()
  })

  it("repart du premier temps quand l'identifiant change", async () => {
    login.mockRejectedValueOnce(refusTotp("Ce champ est obligatoire."))
    afficher()

    saisirIdentifiants()
    await screen.findByLabelText("Code de double authentification")
    fireEvent.change(screen.getByLabelText("Identifiant"), { target: { value: "autre.compte" } })

    expect(screen.queryByLabelText("Code de double authentification")).toBeNull()
  })
})

/**
 * Audit UX du 4 octobre 2026 : la connexion ne présente que ce qui sert à
 * entrer. L'installation se propose après, dans le menu du compte ; la
 * langue se lit sans deviner l'icône.
 */
describe("écran de connexion", () => {
  it("ne présente pas l'installation de l'application", () => {
    afficher()

    expect(screen.queryByText(/Windows|macOS/)).toBeNull()
  })

  it("nomme la langue courante à côté de son icône", () => {
    afficher()

    // Le nom accessible contient le texte visible (WCAG 2.5.3).
    expect(screen.getByRole("button", { name: "FR — Langue de l'interface" })).toHaveTextContent("FR")
  })
})
