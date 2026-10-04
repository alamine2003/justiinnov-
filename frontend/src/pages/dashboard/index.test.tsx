import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DashboardPage } from "./index"
import type { Dashboard, DashboardCountryRow, Me } from "@/lib/types"

const fetchBreakdown = vi.fn()
const fetchDashboard = vi.fn()
const fetchConfiguration = vi.fn()

vi.mock("@/lib/reporting", async (original) => ({
  ...(await original<typeof import("@/lib/reporting")>()),
  fetchDashboard: (...args: unknown[]) => fetchDashboard(...args),
  fetchBreakdown: (...args: unknown[]) => fetchBreakdown(...args),
}))
vi.mock("@/lib/countries", () => ({ fetchCountries: vi.fn(() => Promise.resolve({ count: 0, results: [] })) }))
vi.mock("@/lib/accounts", () => ({
  fetchConfiguration: (...args: unknown[]) => fetchConfiguration(...args),
}))

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
      execution_level: "ok",
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

/** Une ligne pays telle que le serveur la rend, niveau d'exécution compris. */
function lignePays(overrides: Partial<DashboardCountryRow>): DashboardCountryRow {
  return {
    country: 2,
    country_name: "Togo",
    country_ref: "TG",
    currency: "XOF",
    allocated: "1000",
    sub_allocated: "0",
    engaged: "0",
    consumed: "750",
    justified: "750",
    gap: "0",
    remaining: "250",
    execution_rate: "0.75",
    execution_level: "warning",
    justification_rate: "1",
    remaining_xof: "250",
    ...overrides,
  }
}

function monter() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  fetchConfiguration.mockReset()
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

/**
 * Régression : le seuil d'avertissement était recalculé côté client, d'après
 * la configuration — que seuls les administrateurs lisent. Un compte sans
 * accès à la configuration voyait donc une barre à 85 % en azur là où
 * l'administrateur la voyait en ambre, pour les mêmes chiffres. Le serveur tranche désormais (`execution_level`).
 */
describe("Pilotage — teinte du taux d'exécution", () => {
  it("suit le niveau tranché par le serveur, quel que soit le rôle", async () => {
    profil = { role: "super_admin", has_global_scope: true, countries: [] } as Partial<Me>
    fetchDashboard.mockResolvedValue({
      ...tableauDeBord(),
      countries: [
        lignePays({ execution_level: "warning" }),
        lignePays({
          country: 3,
          country_name: "Benin",
          execution_rate: "0.9",
          execution_level: "ok",
        }),
        lignePays({
          country: 4,
          country_name: "Mali",
          execution_rate: "1.2",
          remaining: "-200",
          execution_level: "exceeded",
        }),
      ],
    })

    monter()

    // 75 % en attente et 90 % correct : c'est le seuil du serveur qui le
    // dit — un repli client à 80 % aurait dit l'inverse des deux.
    expect(await screen.findByText("75 %")).toHaveClass("text-statut-attente")
    expect(screen.getByText("90 %")).toHaveClass("text-marque-fort")
    expect(screen.getByText("120 %")).toHaveClass("text-destructive")
    // Plus aucune lecture de la configuration : la teinte ne dépend pas du rôle.
    expect(fetchConfiguration).not.toHaveBeenCalled()
  })
})

/**
 * Régression : l'aide de la tuile « Dossiers ouverts » disait « tous pays »
 * en dur, y compris à un manager qui n'en voit qu'un.
 */
describe("Pilotage — portée des tuiles", () => {
  it("nomme le pays du manager", async () => {
    profil = { has_global_scope: false, countries: [pays(2, "Togo")] } as Partial<Me>

    monter()

    await waitFor(() => expect(fetchDashboard).toHaveBeenCalled())
    expect(screen.getByRole("link", { name: /Dossiers ouverts/ })).toHaveTextContent("Togo")
    expect(screen.queryByText("tous pays")).toBeNull()
  })

  it("garde « tous pays » au siège", async () => {
    profil = { has_global_scope: true, countries: [] } as Partial<Me>

    monter()

    await waitFor(() => expect(fetchDashboard).toHaveBeenCalled())
    expect(screen.getByRole("link", { name: /Dossiers ouverts/ })).toHaveTextContent("tous pays")
  })
})

/**
 * L'analyse d'un pays tient en un panneau : trois onglets, et la répartition
 * se lit un axe à la fois, choisi dans une liste — huit onglets ne tenaient
 * pas sur une ligne et poussaient le panneau hors de l'écran.
 */
describe("Pilotage — analyse d'un pays", () => {
  const ligne = (label: string) => ({ label, lines: 1, amount: "100", justified: "100", gap: "0" })

  it("répartit selon l'axe choisi, un seul tableau à la fois", async () => {
    profil = { has_global_scope: false, countries: [pays(2, "Togo")] } as Partial<Me>
    fetchBreakdown.mockResolvedValue({
      year: 2026,
      by_team: [ligne("Équipe Lomé")],
      by_owner: [],
      by_project: [ligne("Congrès de Lomé")],
      by_project_kind: [],
      by_dossier_kind: [],
      by_category: [],
      by_expense_title: [],
      by_month: [],
    })

    monter()

    fireEvent.click(await screen.findByRole("tab", { name: "Répartition" }))
    const axe = await screen.findByRole("combobox", { name: "Répartir par" })
    expect(screen.getByText("Équipe Lomé")).toBeInTheDocument()
    expect(screen.queryByText("Congrès de Lomé")).toBeNull()

    fireEvent.change(axe, { target: { value: "by_project" } })

    expect(screen.getByText("Congrès de Lomé")).toBeInTheDocument()
    expect(screen.queryByText("Équipe Lomé")).toBeNull()
  })
})

/**
 * Régression : les tuiles ouvraient le registre sans l'exercice ni le pays
 * qu'elles comptaient — la liste ne disait pas le chiffre de la tuile.
 */
describe("Pilotage — liens des tuiles", () => {
  it("transmettent l'exercice et le pays au registre", async () => {
    profil = { has_global_scope: false, countries: [pays(2, "Togo")] } as Partial<Me>

    monter()

    const lien = await screen.findByRole("link", { name: /Lignes en brouillon/ })
    const adresse = new URL(lien.getAttribute("href") ?? "", "http://x")
    expect(adresse.pathname).toBe("/registre")
    expect(adresse.searchParams.get("status")).toBe("draft")
    expect(adresse.searchParams.get("from")).toMatch(/^\d{4}-01-01$/)
    expect(adresse.searchParams.get("to")).toMatch(/^\d{4}-12-31$/)
  })
})

/**
 * Régression : sous le bandeau d'erreur, les tuiles affichaient « 0 » et
 * le panneau « aucune enveloppe » — un échec se lisait comme un résultat.
 */
describe("Pilotage — chargement en échec", () => {
  it("n'affiche aucun zéro ni état vide", async () => {
    profil = { has_global_scope: false, countries: [pays(2, "Togo")] } as Partial<Me>
    fetchDashboard.mockRejectedValue(new Error("Service indisponible"))

    monter()

    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Lignes en brouillon/ })).toHaveTextContent("—")
    expect(screen.getByRole("link", { name: /Lignes en brouillon/ })).not.toHaveTextContent("0")
    expect(screen.queryByText(/Aucune enveloppe/)).toBeNull()
  })
})
