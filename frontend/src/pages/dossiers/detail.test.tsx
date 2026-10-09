import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { Link, MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { DossierDetailPage } from "./detail"
import type { Dossier } from "@/lib/types"

// La ligne 7 du dossier 20 porte un intitulé et un bénéficiaire désactivés
// depuis sa saisie.
const LIGNE = {
  id: 7,
  title: "Kakémonos",
  expense_title: 31,
  beneficiary: 41,
  beneficiary_name: "Imprimerie fermée",
  allowed_actions: ["edit"],
}

/** Un dossier tel que le serveur le rend, réduit à ce que la fiche lit. */
function dossier(id: number): Dossier {
  return {
    id,
    number: `TG-P-2026-001-D00${id}`,
    label: `Dossier ${id}`,
    status: "draft",
    status_display: "Brouillon",
    allowed_actions: [],
    country: 2,
    country_name: "Togo",
    country_ref: "TG-01",
    country_timezone: "Africa/Lome",
    currency: "XOF",
    date: "2026-10-01",
    created_by: "togo.ci",
    owner_name: "",
    project: 1,
    project_name: "Congrès",
    project_is_historical: false,
    kind_name: "Stands",
    team: null,
    team_name: null,
    note: "",
    reopen_note: "",
    lignes_sans_preuve: 0,
    expenses: id === 20 ? [LIGNE] : [],
    proofs: [],
    totals: { amount: "0", justified: "0", gap: "0" },
  } as unknown as Dossier
}

const fetchRectifications = vi.fn(() =>
  Promise.resolve({ count: 0, next: null, previous: null, results: [] }),
)
vi.mock("@/lib/expenses", async (original) => ({
  ...(await original<typeof import("@/lib/expenses")>()),
  fetchDossier: (id: number) => Promise.resolve(dossier(id)),
  fetchRectifications: () => fetchRectifications(),
  fetchBeneficiaries: () => Promise.resolve({ count: 0, next: null, previous: null, results: [] }),
}))
vi.mock("@/lib/countries", () => ({
  fetchCountry: () =>
    Promise.resolve({
      id: 2,
      currency_symbol: "FCFA",
      teams: [],
      managers: [],
      projects: [],
      marketing_categories: [],
      expense_titles: [
        { id: 30, name: "Impression", is_active: true },
        { id: 31, name: "Ancien intitulé", is_active: false },
      ],
    }),
}))
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ me: { has_global_scope: false, teams: [] }, can: () => false }),
}))
// Les actions du circuit : un refus du serveur, sans dépendre du dialogue.
vi.mock("@/components/expenses/workflow-actions", () => ({
  WorkflowActions: ({ onError }: { onError: (message: string) => void }) => (
    <button type="button" onClick={() => onError("Refus propre à ce dossier.")}>
      Déclencher un refus
    </button>
  ),
}))

// La carte de ligne ouvre l'édition ; le formulaire montre les choix reçus.
vi.mock("@/components/expenses/expense-line-card", () => ({
  CarteDeLigne: ({
    expense,
    onEdit,
    onTrashed,
  }: {
    expense: { title: string }
    onEdit: (e: unknown) => void
    onTrashed: (e: unknown) => void
  }) => (
    <li>
      <button type="button" onClick={() => onEdit(expense)}>
        Modifier {expense.title}
      </button>
      <button type="button" onClick={() => onTrashed(expense)}>
        Retirer {expense.title}
      </button>
    </li>
  ),
}))
vi.mock("@/components/expenses/expense-form", () => ({
  ExpenseForm: ({
    open,
    expenseTitles,
    beneficiaries,
  }: {
    open: boolean
    expenseTitles: { name: string }[]
    beneficiaries: { name: string }[]
  }) =>
    open ? (
      <ul aria-label="Choix du formulaire">
        {[...expenseTitles, ...beneficiaries].map((o) => (
          <li key={o.name}>{o.name}</li>
        ))}
      </ul>
    ) : null,
}))

/**
 * Régression : la page restait montée d'un dossier à l'autre, et l'erreur
 * ou l'avertissement du 12 s'affichaient sur le 13 — ouvert depuis une
 * notification ou par « Retour ».
 */
describe("fiche d'un dossier", () => {
  it("n'emporte pas l'erreur d'un dossier sur le suivant", async () => {
    render(
      <MemoryRouter initialEntries={["/dossiers/12"]}>
        <Link to="/dossiers/13">Aller au 13</Link>
        <Routes>
          <Route path="/dossiers/:id" element={<DossierDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole("button", { name: "Déclencher un refus" }))
    expect(await screen.findByText("Refus propre à ce dossier.")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("link", { name: "Aller au 13" }))

    expect(await screen.findByRole("heading", { name: "Dossier 13" })).toBeInTheDocument()
    expect(screen.queryByText("Refus propre à ce dossier.")).toBeNull()
  })

  it("garde l'intitulé et le bénéficiaire désactivés de la ligne qu'on modifie", async () => {
    render(
      <MemoryRouter initialEntries={["/dossiers/20"]}>
        <Routes>
          <Route path="/dossiers/:id" element={<DossierDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole("button", { name: "Modifier Kakémonos" }))

    const choix = await screen.findByRole("list", { name: "Choix du formulaire" })
    expect(choix).toHaveTextContent("Impression")
    expect(choix).toHaveTextContent("Ancien intitulé")
    expect(choix).toHaveTextContent("Imprimerie fermée")
  })

  it("après la corbeille d'une ligne, relit ses rectifications et le dit sans parler de budget", async () => {
    render(
      <MemoryRouter initialEntries={["/dossiers/20"]}>
        <Routes>
          <Route path="/dossiers/:id" element={<DossierDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole("button", { name: "Retirer Kakémonos" }))

    expect(await screen.findByText("« Kakémonos » est dans la corbeille.")).toBeInTheDocument()
    expect(screen.getByText("Mis à la corbeille")).toBeInTheDocument()
    expect(screen.queryByText("Avertissement budgétaire")).toBeNull()
    // Les demandes de la ligne sont parties avec elle : le rail se relit.
    await waitFor(() => expect(fetchRectifications.mock.calls.length).toBeGreaterThanOrEqual(2))
  })
})
