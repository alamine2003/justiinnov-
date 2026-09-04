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

  it("montre le champ du code dès l'écran de connexion, facultatif tant que le serveur ne l'exige pas", () => {
    afficher()

    const champ = screen.getByLabelText("Code de double authentification")
    expect(champ).toBeInTheDocument()
    expect(champ).not.toBeRequired()
  })

  it("se connecte en une seule fois quand le code est saisi d'emblée", async () => {
    login.mockResolvedValueOnce(undefined)
    afficher()

    fireEvent.change(screen.getByLabelText("Code de double authentification"), {
      target: { value: "654321" },
    })
    saisirIdentifiants()

    await waitFor(() => expect(login).toHaveBeenCalledWith("togo.innov", "secret", "654321"))
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
