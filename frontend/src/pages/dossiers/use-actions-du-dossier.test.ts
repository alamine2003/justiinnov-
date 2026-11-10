import { act, renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { DossierDetail, Expense, Paginated, Rectification } from "@/lib/types"
import type { QueryResult } from "@/lib/use-query"
import { useActionsDuDossier } from "@/pages/dossiers/use-actions-du-dossier"

const transitionDossier = vi.fn()
const transitionExpense = vi.fn()
const reopenDossier = vi.fn()
const renameDossier = vi.fn()
const requestRectification = vi.fn()
const deleteExpenseDraft = vi.fn()

vi.mock("@/lib/expenses", () => ({
  transitionDossier: (...args: unknown[]) => transitionDossier(...args),
  transitionExpense: (...args: unknown[]) => transitionExpense(...args),
  reopenDossier: (...args: unknown[]) => reopenDossier(...args),
  renameDossier: (...args: unknown[]) => renameDossier(...args),
  requestRectification: (...args: unknown[]) => requestRectification(...args),
  deleteExpenseDraft: (...args: unknown[]) => deleteExpenseDraft(...args),
}))

const LIGNE = { id: 5, title: "Hôtel" } as Expense
const DOSSIER = { id: 12, expenses: [LIGNE] } as unknown as DossierDetail

function requete<T>(data: T | null): QueryResult<T> {
  return {
    data,
    loading: false,
    refreshing: false,
    error: null,
    retryAfter: null,
    reload: vi.fn(),
    setData: vi.fn(),
  }
}

function monter() {
  const query = requete(DOSSIER)
  const rectifications = requete<Paginated<Rectification>>(null)
  const rendu = renderHook(() =>
    useActionsDuDossier({ dossierId: 12, dossier: DOSSIER, query, rectifications }),
  )
  return { ...rendu, query, rectifications }
}

describe("useActionsDuDossier", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    transitionDossier.mockResolvedValue({ ...DOSSIER, warning: "Enveloppe dépassée" })
    transitionExpense.mockResolvedValue({ ...LIGNE })
    renameDossier.mockResolvedValue({ ...DOSSIER, label: "Nouveau titre" })
  })

  it("garde l'avertissement du serveur, puis l'efface à l'action suivante", async () => {
    const { result } = monter()
    await act(() => result.current.runDossierTransition("submit"))
    expect(result.current.notice).toBe("Enveloppe dépassée")

    await act(() => result.current.rename("Nouveau titre"))
    expect(result.current.notice).toBeNull()
    expect(renameDossier).toHaveBeenCalledWith(12, "Nouveau titre")
  })

  it("efface erreur, avertissement et avis de corbeille d'un coup", async () => {
    const { result } = monter()
    await act(() => result.current.runDossierTransition("submit"))
    act(() => {
      result.current.setActionError("Refusé")
      result.current.ligneALaCorbeille(LIGNE)
    })
    expect(result.current.retiree).not.toBeNull()

    act(() => {
      result.current.setActionError("Refusé")
      result.current.effacerLesMessages()
    })
    expect(result.current.actionError).toBeNull()
    expect(result.current.notice).toBeNull()
    expect(result.current.retiree).toBeNull()
  })

  it("relance le refus d'une transition au bouton qui l'a demandée", async () => {
    transitionExpense.mockRejectedValueOnce(new Error("Pièce manquante"))
    const { result } = monter()
    await expect(
      act(() => result.current.runExpenseTransition(LIGNE, "justify")),
    ).rejects.toThrow("Pièce manquante")
    expect(result.current.actionError).toBeNull()
  })

  it("au retrait d'un brouillon, n'efface que l'erreur et montre la sienne", async () => {
    deleteExpenseDraft.mockRejectedValueOnce(new Error("Déjà soumis"))
    const { result, query } = monter()
    await act(() => result.current.runDossierTransition("submit"))

    await act(() => result.current.removeDraft(LIGNE))
    expect(result.current.actionError).toBe("Déjà soumis")
    expect(result.current.notice).toBe("Enveloppe dépassée")
    expect(result.current.deletingId).toBeNull()

    deleteExpenseDraft.mockResolvedValueOnce(undefined)
    await act(() => result.current.removeDraft(LIGNE))
    expect(result.current.actionError).toBeNull()
    expect(query.setData).toHaveBeenCalled()
    expect(query.reload).toHaveBeenCalled()
  })

  it("relit le dossier et ses rectifications après une demande ou une décision", async () => {
    const { result, query, rectifications } = monter()
    await act(() => result.current.requestLineRectification(LIGNE, "Montant faux"))
    expect(requestRectification).toHaveBeenCalledWith(5, "Montant faux")
    expect(query.reload).toHaveBeenCalledTimes(1)
    expect(rectifications.reload).toHaveBeenCalledTimes(1)

    await act(() => result.current.afterRectificationDecided())
    expect(query.reload).toHaveBeenCalledTimes(2)
    expect(rectifications.reload).toHaveBeenCalledTimes(2)
  })
})
