import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { RegisterPage } from "./index"
import type { Me } from "@/lib/types"

const fetchRegister = vi.fn()

vi.mock("@/lib/expenses", () => ({ fetchRegister: (...args: unknown[]) => fetchRegister(...args) }))
vi.mock("@/lib/countries", () => ({
  fetchCountries: vi.fn(() => Promise.resolve({ count: 0, results: [] })),
}))

let profil: Partial<Me> = {}
vi.mock("@/context/use-auth", () => ({ useAuth: () => ({ me: profil, can: () => false }) }))

const pays = (id: number, name: string, timezone: string) => ({
  id,
  name,
  code: name.slice(0, 2).toUpperCase(),
  country_ref: null,
  timezone,
  currency: "XOF",
})

const ABIDJAN = "Africa/Abidjan"
const TANANARIVE = "Indian/Antananarivo"

function monter() {
  return render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  profil = {}
  fetchRegister.mockReset().mockResolvedValue({ count: 0, results: [] })
})

/**
 * Régression, jumelle de celle du Pilotage : le registre réservait le
 * sélecteur de pays au périmètre global et, pour les autres, lisait les
 * bornes de période dans le fuseau de `countries[0]` — arbitraire dès que le
 * périmètre en compte deux.
 */
describe("Registre — périmètre restreint à plusieurs pays", () => {
  it("propose le sélecteur de pays", async () => {
    profil = {
      has_global_scope: false,
      countries: [pays(1, "Cote d'Ivoire", ABIDJAN), pays(2, "Madagascar", TANANARIVE)],
    } as Partial<Me>

    monter()

    await waitFor(() => expect(fetchRegister).toHaveBeenCalled())
    expect(screen.getByLabelText("Pays")).toBeInTheDocument()
    expect(screen.getByRole("option", { name: /Madagascar/ })).toBeInTheDocument()
  })

  it("n'affirme aucun fuseau tant qu'aucun pays n'est déterminé", async () => {
    profil = {
      has_global_scope: false,
      countries: [pays(1, "Cote d'Ivoire", ABIDJAN), pays(2, "Madagascar", TANANARIVE)],
    } as Partial<Me>

    monter()

    await waitFor(() => expect(fetchRegister).toHaveBeenCalled())
    // Le libellé annonçait « Du (heure Indian/Antananarivo) » à un compte qui
    // couvre aussi Abidjan : un fuseau vrai pour la moitié de son périmètre.
    expect(screen.getByText("Du")).toBeInTheDocument()
    expect(screen.queryByText(`Du (heure ${TANANARIVE})`)).toBeNull()
  })

  it("garde le fuseau du pays quand le périmètre n'en compte qu'un", async () => {
    profil = { has_global_scope: false, countries: [pays(2, "Togo", "Africa/Lome")] } as Partial<Me>

    monter()

    await waitFor(() => expect(fetchRegister).toHaveBeenCalled())
    expect(screen.getByText("Du (heure Africa/Lome)")).toBeInTheDocument()
    expect(screen.queryByLabelText("Pays")).toBeNull()
  })
})
