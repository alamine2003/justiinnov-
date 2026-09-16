import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DashboardPage } from "./index"
import type { Dashboard, Me } from "@/lib/types"

const fetchBreakdown = vi.fn()
const fetchDashboard = vi.fn()

vi.mock("@/lib/reporting", async (original) => ({
  ...(await original<typeof import("@/lib/reporting")>()),
  fetchDashboard: (...args: unknown[]) => fetchDashboard(...args),
  fetchBreakdown: (...args: unknown[]) => fetchBreakdown(...args),
}))
vi.mock("@/lib/countries", () => ({ fetchCountries: vi.fn(() => Promise.resolve({ count: 0, results: [] })) }))
vi.mock("@/lib/accounts", () => ({ fetchConfiguration: vi.fn() }))

let profil: Partial<Me> = {}
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ me: profil, can: () => false }),
}))

/** Le tableau de bord tel que le serveur le rend, sur un exercice vide. */
function tableauDeBord(): Dashboard {
  return {
    year: 2026,
    totals: {
      currency: "XOF",
      allocated: "0",
      engaged: "0",
      consumed: "0",
      justified: "0",
      gap: "0",
      remaining: "0",
      execution_rate: "0",
      justification_rate: "0",
      unconverted_currencies: [],
    },
    consolidated_xof: { allocated: "0", remaining: "0", unconverted_currencies: [] },
    countries: [],
    workload: {
      expenses_to_review: 0,
      expenses_draft: 0,
      expenses_unjustified: 0,
      dossiers_open: 0,
    },
    alerts: [],
    alerts_total: 0,
  }
}

const pays = (id: number, name: string) => ({ id, name, code: name.slice(0, 2).toUpperCase(), country_ref: null, timezone: "Africa/Abidjan", currency: "XOF" })

function monter() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  fetchDashboard.mockReset().mockResolvedValue(tableauDeBord())
  fetchBreakdown.mockReset().mockResolvedValue({
    year: 2026,
    by_team: [],
    by_owner: [],
    by_project: [],
    by_category: [],
    by_expense_title: [],
    by_month: [],
  })
})

/**
 * Régression : la page supposait que « pas de périmètre global » valait « un
 * seul pays ». Le serveur ne devine le pays que lorsqu'il n'y en a qu'un
 * (`_pays_unique`) et répond 400 sinon ; les deux appels étant dans un
 * `Promise.all`, tout le tableau de bord disparaissait — et le sélecteur de
 * pays, réservé au périmètre global, ne permettait pas de s'en sortir.
 */
describe("Pilotage — périmètre restreint à plusieurs pays", () => {
  it("ne demande pas la répartition sans nommer le pays", async () => {
    profil = { has_global_scope: false, countries: [pays(1, "Cote d'Ivoire"), pays(2, "Togo")] } as Partial<Me>

    monter()

    await waitFor(() => expect(fetchDashboard).toHaveBeenCalled())
    expect(fetchBreakdown).not.toHaveBeenCalled()
  })

  it("propose le sélecteur de pays pour que le compte en nomme un", async () => {
    profil = { has_global_scope: false, countries: [pays(1, "Cote d'Ivoire"), pays(2, "Togo")] } as Partial<Me>

    monter()

    await waitFor(() => expect(fetchDashboard).toHaveBeenCalled())
    expect(screen.getByRole("combobox", { name: "Pays" })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: /Togo/ })).toBeInTheDocument()
  })

  it("laisse le serveur deviner le pays quand le périmètre n'en compte qu'un", async () => {
    profil = { has_global_scope: false, countries: [pays(2, "Togo")] } as Partial<Me>

    monter()

    await waitFor(() => expect(fetchBreakdown).toHaveBeenCalled())
    expect(screen.queryByRole("combobox", { name: "Pays" })).toBeNull()
  })

  it("garde le tableau de bord debout quand la répartition est refusée", async () => {
    profil = { has_global_scope: false, countries: [pays(2, "Togo")] } as Partial<Me>
    fetchBreakdown.mockRejectedValue(new Error("Le pays est obligatoire."))

    monter()

    await waitFor(() => expect(fetchDashboard).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText("Le pays est obligatoire.")).toBeNull())
  })
})
