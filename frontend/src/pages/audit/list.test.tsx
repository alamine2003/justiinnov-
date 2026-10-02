import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AuditPage } from "./list"
import type { AuditEntry, SyntheseAudit } from "@/lib/types"

const fetchAudit = vi.fn()
const fetchAuditSynthese = vi.fn()
const fetchHistory = vi.fn()
vi.mock("@/lib/expenses", () => ({
  fetchAudit: (...args: unknown[]) => fetchAudit(...args),
  fetchAuditSynthese: (...args: unknown[]) => fetchAuditSynthese(...args),
}))
vi.mock("@/lib/countries", () => ({
  fetchCountries: vi.fn(() => Promise.resolve({ count: 0, results: [] })),
  fetchHistory: (...args: unknown[]) => fetchHistory(...args),
}))
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ me: { has_global_scope: true }, can: () => true }),
}))

function afficher(adresse: string) {
  return render(
    <MemoryRouter initialEntries={[adresse]}>
      <Routes>
        <Route path="/audit" element={<AuditPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

function entree(detail: Record<string, unknown>, extra: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: 1,
    user: "rh.innov",
    action: "submitted",
    action_display: "Soumis",
    object_type: "Expense",
    object_id: 7,
    label: "Hôtel Abidjan",
    country: 1,
    country_name: "Côte d'Ivoire",
    detail,
    ip_address: "10.0.0.1",
    user_agent: "",
    created_at: "2026-03-15T08:30:00Z",
    ...extra,
  } as unknown as AuditEntry
}

const COMPTEURS: SyntheseAudit["compteurs"] = {
  circuit: 42, referentiel: 9, declarations: 3, decisions: 5, reouvertures: 1,
  rectifications: 2, refus: 4, pieces: 6, sorties: 7, imports: 0, suppressions: 0,
  renommages: 1, changements_de_droits: 1, echecs_de_connexion: 8,
  reinitialisations_2fa: 0, desactivations: 0, projets: 2,
}

function synthese(): SyntheseAudit {
  return {
    debut: "2026-09-03",
    fin: "2026-10-02",
    compteurs: COMPTEURS,
    par_jour: [{ jour: "2026-10-01", circuit: 30, referentiel: 4 }],
    par_utilisateur: [{ user: "owner.togo", count: 17 }],
    par_pays: [{ country: 2, name: "Togo", count: 40 }],
    a_surveiller: [
      {
        source: "circuit", id: 5, action: "reopened", action_display: "Réouverture",
        objet: "Dossier", object_id: 11, label: "Stands", user: "rh.innov",
        ip_address: "10.1.2.3", motif: "", avant: null, apres: null,
        note: "Facture illisible", created_at: "2026-10-01T09:00:00Z",
      },
    ],
  } as SyntheseAudit
}

beforeEach(() => {
  fetchAudit.mockReset()
  fetchAuditSynthese.mockReset()
  fetchHistory.mockReset()
})

describe("Audit — vue d'ensemble", () => {
  it("affiche les chiffres tels que le serveur les rend, sans rien recompter", async () => {
    fetchAuditSynthese.mockResolvedValue(synthese())

    afficher("/audit")

    await screen.findByText("Dossiers soumis")
    expect(screen.getByText("8")).toBeInTheDocument()
    expect(screen.getByText("Échecs de connexion")).toBeInTheDocument()
    expect(screen.getByText("owner.togo")).toBeInTheDocument()
    expect(screen.getByText("17")).toBeInTheDocument()
    // Le total vient du serveur (42), pas d'une somme des tuiles.
    expect(screen.getByText(/42 événement/)).toBeInTheDocument()
    // « À surveiller » : l'événement en clair, avec sa note.
    expect(screen.getByText("Facture illisible")).toBeInTheDocument()
  })

  it("une tuile mène au journal filtré, période comprise", async () => {
    fetchAuditSynthese.mockResolvedValue(synthese())

    afficher("/audit?debut=2026-09-01&fin=2026-09-30")

    const tuile = (await screen.findByText("Réouvertures")).closest("a")
    expect(tuile).not.toBeNull()
    const lien = new URL(tuile!.getAttribute("href")!, "http://x")
    expect(Object.fromEntries(lien.searchParams)).toEqual({
      debut: "2026-09-01", fin: "2026-09-30", onglet: "circuit",
      action: "reopened", object_type: "Dossier",
    })
    expect(fetchAuditSynthese).toHaveBeenCalledWith(
      { debut: "2026-09-01", fin: "2026-09-30" }, expect.anything(),
    )
  })
})

/**
 * Régression : le détail d'une entrée sortait brut — « draft → submitted » et
 * « 1500.00 → 1200.00 », en français comme en anglais. La règle « aucune
 * chaîne visible en dur » était contournée parce que la chaîne venait de la
 * donnée plutôt que du code, et le garde-fou anti-chaînes-en-dur ne voit que
 * les accents.
 */
describe("Audit — journal du circuit", () => {
  it("traduit les statuts du circuit", async () => {
    fetchAudit.mockResolvedValue({
      count: 1,
      results: [entree({ from_status: "draft", to_status: "submitted" })],
    })

    afficher("/audit?onglet=circuit")

    await waitFor(() => expect(screen.getByText("Brouillon → Soumis")).toBeInTheDocument())
    expect(screen.queryByText("draft → submitted")).toBeNull()
  })

  it("formate les montants", async () => {
    fetchAudit.mockResolvedValue({
      count: 1,
      results: [
        entree({ before: { amount: "1500000.00" }, after: { amount: "1200000.00" } }),
      ],
    })

    afficher("/audit?onglet=circuit")

    await waitFor(() => expect(fetchAudit).toHaveBeenCalled())
    expect(screen.getByText(/1 500 000/)).toBeInTheDocument()
    expect(screen.queryByText(/1500000\.00/)).toBeNull()
  })

  it("montre l'ancien et le nouveau titre d'un renommage", async () => {
    fetchAudit.mockResolvedValue({
      count: 1,
      results: [
        entree(
          { before: { label: "Stands" }, after: { label: "Stands du hall A" } },
          { action: "renamed", action_display: "Renommage", object_type: "Dossier" },
        ),
      ],
    })

    afficher("/audit?onglet=circuit")

    expect(await screen.findByText("Stands du hall A")).toBeInTheDocument()
    expect(screen.getByText("Stands")).toBeInTheDocument()
  })

  it("passe les filtres de l'adresse à l'API, projet compris", async () => {
    fetchAudit.mockResolvedValue({ count: 0, results: [] })

    afficher("/audit?onglet=circuit&projet=7&action=reopened&country=2&debut=2026-09-01")

    await waitFor(() =>
      expect(fetchAudit).toHaveBeenCalledWith(
        expect.objectContaining({
          projet: "7", action: "reopened", country: "2", debut: "2026-09-01", page: 1,
        }),
        expect.anything(),
      ),
    )
  })

  it("propose le renommage parmi les actions", async () => {
    fetchAudit.mockResolvedValue({ count: 0, results: [] })

    afficher("/audit?onglet=circuit")

    await waitFor(() => expect(fetchAudit).toHaveBeenCalled())
    expect(screen.getByRole("option", { name: "Renommage" })).toBeInTheDocument()
  })
})

describe("Audit — référentiel et comptes", () => {
  it("lit l'historique avec ses filtres et montre le motif", async () => {
    fetchHistory.mockResolvedValue({
      count: 1,
      results: [
        {
          id: 3, model_name: "project", model_name_display: "Projet", object_id: 9,
          label: "Congrès de Lomé 2026", action: "updated", action_display: "Mise à jour",
          from_value: "", to_value: "", changed_fields: ["name"],
          diff: { name: ["Congrès de Lomé", "Congrès de Lomé 2026"] },
          performed_by: "owner.togo", ip_address: "10.0.0.2", country: 2,
          country_name: "Togo", motif: "Année oubliée", created_at: "2026-10-01T08:00:00Z",
        },
      ],
    })

    afficher("/audit?onglet=referentiel&model_name=project")

    expect(await screen.findByText("Année oubliée")).toBeInTheDocument()
    expect(fetchHistory).toHaveBeenCalledWith(
      expect.objectContaining({ model_name: "project", page: 1 }), expect.anything(),
    )
    fireEvent.change(screen.getByRole("textbox", { name: "Rechercher dans l'historique" }), {
      target: { value: "oubli" },
    })
    await waitFor(() =>
      expect(fetchHistory).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "oubli" }), expect.anything(),
      ),
    )
  })
})
